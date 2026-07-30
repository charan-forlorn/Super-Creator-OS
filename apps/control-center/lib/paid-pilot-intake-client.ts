
import type { IntakeResponse } from "./paid-pilot-intake-types";
async function post(operation:string, body:Record<string,unknown>):Promise<IntakeResponse>{
  try{const res=await fetch("/api/paid-pilot/intake",{method:"POST",cache:"no-store",headers:{"content-type":"application/json"},body:JSON.stringify({operation,...body})}); const d=await res.json() as IntakeResponse; return {ok:Boolean(d.ok),error_code:d.error_code??null,detail:d.detail??null,draft:d.draft??null,replay:d.replay,pilot_safe_id:d.pilot_safe_id,project_safe_id:d.project_safe_id,admission_packet_sha256:d.admission_packet_sha256,next_safe_action:d.next_safe_action};}
  catch(e){return {ok:false,error_code:"REQUEST_FAILED",detail:e instanceof Error?e.message:"unknown",draft:null};}
}
export const createIntakeDraft=(body:Record<string,unknown>)=>post("draft",body);
export const attachConsentEvidence=(draftId:string, safeReference:string, evidenceText:string, explicit:boolean)=>post("consent",{draft_id:draftId,safe_reference:safeReference,evidence_text:evidenceText,explicit_consent_confirmed:explicit});
export const validateIntakeDraft=(draftId:string)=>post("validate",{draft_id:draftId});
export const getIntakeDraft=(draftId:string)=>post("get",{draft_id:draftId});
export const createPilotFromDraft=(draftId:string,idempotencyKey:string)=>post("create",{draft_id:draftId,idempotency_key:idempotencyKey});

export const refreshAssetInventory=(draftId:string)=>post("sample-asset",{draft_id:draftId});

// Cohort 10K — plain-language Brief Studio. Reuses this reviewed same-origin
// transport; the browser never becomes an authoritative writer.
export const saveBriefSection=(draftId:string, sectionId:string, answers:Record<string,string>)=>post("brief-section",{draft_id:draftId,section_id:sectionId,answers});
export const updateIntakeDraft=(draftId:string, updates:Record<string,unknown>)=>post("update",{draft_id:draftId,updates});
