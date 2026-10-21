/** Pure, fail-closed diagnostic for CFIT private AI shot decisions.
 * No source URLs, tokens, personal data or storage paths are accepted or logged.
 * Integration target: existing cfit-int-render-dispatch-test Edge Function.
 */
export type Shot = {source_id?: unknown; start?: unknown; end?: unknown; purpose?: unknown};
export type ShotFailure = {source_id: string; reasons: string[]; source_duration?: number; start?: number; end?: number};
export function validatePrivateShots(
  shots: unknown,
  approvedSourceIds: string[],
  durationById: Record<string, number>
): {valid: boolean; failures: ShotFailure[]; missingSources: string[]} {
  if (!Array.isArray(shots)) return {valid:false, failures:[{source_id:"",reasons:["shots_not_array"]}],missingSources:approvedSourceIds};
  const failures:ShotFailure[]=[];
  for (const candidate of shots) {
    const s:Shot=candidate&&typeof candidate==="object"?candidate:{};
    const id=typeof s.source_id==="string"?s.source_id:"";
    const reasons:string[]=[];
    if(!approvedSourceIds.includes(id)) reasons.push("unapproved_source");
    const start=typeof s.start==="number"&&Number.isFinite(s.start)?s.start:undefined;
    const end=typeof s.end==="number"&&Number.isFinite(s.end)?s.end:undefined;
    if(start===undefined||end===undefined) reasons.push("nonfinite_or_nonnumeric_time");
    else {
      if(start<0) reasons.push("negative_start");
      if(end<=start) reasons.push("end_not_after_start");
      if(end-start<1) reasons.push("shot_under_one_second");
      if(end-start>18) reasons.push("shot_over_eighteen_seconds");
    }
    const duration=durationById[id];
    if(!Number.isFinite(duration)||duration<=0) reasons.push("unknown_source_duration");
    else if(end!==undefined && end>duration) reasons.push("end_exceeds_original_duration");
    if(typeof s.purpose!=="string"||!s.purpose.trim()) reasons.push("missing_editorial_purpose");
    if(reasons.length) failures.push({
      source_id:id, reasons,
      ...(Number.isFinite(duration)?{source_duration:Number(duration.toFixed(3))}:{}),
      ...(start!==undefined?{start:Number(start.toFixed(3))}:{}),
      ...(end!==undefined?{end:Number(end.toFixed(3))}:{})
    });
  }
  const missingSources=approvedSourceIds.filter(id=>!shots.some((s:Shot)=>s?.source_id===id));
  if(shots.length<approvedSourceIds.length||shots.length>18)failures.push({source_id:"",reasons:["invalid_shot_count"]});
  return {valid:failures.length===0&&missingSources.length===0,failures,missingSources};
}
