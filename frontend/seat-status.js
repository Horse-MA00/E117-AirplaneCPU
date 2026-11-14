/** Separate forecast capacity, issued inventory and today's release decision. */
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const clamp = (value, maximum) => Math.max(0, Math.min(maximum, number(value)));
const rounds = [28, 14, 7];

export function seatStatus(forecast, capacity, normalBooked, day) {
  const inventory=forecast.seat_inventory;
  if(inventory){
    const result={capacity:inventory.capacity,normal:inventory.normal_booked,sold:inventory.member_booked,
      occupied:inventory.occupied,physicalRemaining:inventory.physical_available,protection:inventory.normal_protected,
      headroom:inventory.member_headroom,published:inventory.published_bookable,unpublished:inventory.unpublished_headroom,
      newSeats:inventory.new_releasable_today,held:inventory.held_seats,nextRound:inventory.next_release_day,reason:inventory.release_reason,
      heldPublished:number(inventory.held_published_headroom),confirmedMembers:inventory.confirmed_member_bookings??inventory.member_booked,
      reportedOccupied:inventory.reported_occupied??inventory.occupied,overage:number(inventory.member_inventory_overage),
      releaseState:inventory.release_state,historical:forecast.release_status?.historical_view||inventory.release_state==='historical_view',
      salesClosed:forecast.release_status?.sales_cutoff_passed||inventory.release_state==='sales_closed'};
    result.parts=[
      {key:'occupied',label:'Booked (normal + member)',value:result.occupied},
      {key:'protected',label:'Protected for normal demand',value:result.protection},
      {key:'published',label:'Published, bookable now',value:result.published},
      {key:'available',label:'Safe for members, not yet published',value:result.unpublished},
      {key:'published-held',label:'Published quota on hold',value:Math.min(result.heldPublished,result.held)},
      {key:'held',label:'Held by other safety limits',value:Math.max(0,result.held-result.heldPublished)},
    ];
    return result;
  }
  const r=forecast.release_status||{},c=Math.max(0,number(capacity));
  const normal=clamp(normalBooked,c),sold=clamp(r.member_sold,c-normal),occupied=normal+sold;
  const physicalRemaining=c-occupied;
  const protection=clamp(Math.ceil(number(forecast.protection_p90)),physicalRemaining);
  const surplus=physicalRemaining-protection;
  const riskCeiling=r.safe_capacity??Math.max(0,number(forecast.risk_release_ceiling??forecast.releasable_seats)-sold);
  const headroom=clamp(riskCeiling,surplus);
  const published=clamp(r.currently_bookable??Math.min(number(r.total_active_unsold),headroom),headroom);
  const unpublished=headroom-published,held=surplus-headroom;
  const onRound=rounds.includes(day),nextRound=rounds.find(d=>d<day);
  const newSeats=onRound&&!r.blocked_reason&&!r.round_already_issued
    ?clamp(Math.min(number(forecast.releasable_seats),number(r.new_release_limit??forecast.releasable_seats)),unpublished):0;
  let reason;
  if(day===0)reason='Sales cutoff: no new releases or bookings.';
  else if(r.blocked_reason)reason=`Release paused: ${String(r.blocked_reason).replaceAll('_',' ')}.`;
  else if(r.round_already_issued)reason=`D${day} was already published. This round cannot issue more seats.`;
  else if(!onRound)reason=`${headroom} seats of forecast headroom; ${nextRound?`next release D${nextRound}`:'no release rounds remain'}. No new quota at D${day}.`;
  else if(newSeats>0)reason=`${newSeats} additional seats can be issued at D${day}, after deducting valid unsold quota.`;
  else if(headroom>0&&number(r.total_active_unsold)>=headroom)reason='Earlier valid quota already covers the safe capacity. No duplicate seats will be issued.';
  else if(headroom===0)reason='Normal-demand protection or the current safety limit leaves no member headroom. Try another flight or release round.';
  else reason='The current quota and safety checks allow no additional release.';
  if(day>0&&published>0)reason+=` ${published} already-published seats remain bookable.`;
  const parts=[
    {key:'occupied',label:'Booked (normal + member)',value:occupied},
    {key:'protected',label:'Protected for normal demand',value:protection},
    {key:'published',label:'Published, bookable now',value:published},
    {key:'available',label:'Safe for members, not yet published',value:unpublished},
    {key:'held',label:'Held by other safety limits',value:held},
  ];
  return {capacity:c,normal,sold,occupied,physicalRemaining,protection,headroom,published,unpublished,newSeats,held,nextRound,reason,parts,
    heldPublished:0,confirmedMembers:number(r.member_sold),reportedOccupied:normal+number(r.member_sold),overage:Math.max(0,normal+number(r.member_sold)-c),
    historical:Boolean(r.historical_view),salesClosed:day===0||Boolean(r.sales_cutoff_passed),releaseState:r.round_already_issued?'round_already_issued':undefined};
}
