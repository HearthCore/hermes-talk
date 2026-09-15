"""Offline typed-panel state, captured requests and recipient behavior."""

import runpy
from pathlib import Path
from subprocess import run

import pytest
from test_dashboard_js import NODE_TIMEOUT_S, PAGE_HARNESS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def source_bundle(tmp_path_factory):
    builder = runpy.run_path(str(ROOT / "scripts/build_ui.py"))
    source = builder["render_bundles"](ROOT)[ROOT / "dashboard/dist/index.js"]
    output = tmp_path_factory.mktemp("typed-panel") / "index.js"
    output.write_text(source, encoding="utf-8")
    return output


HARNESS = PAGE_HARNESS + r"""
function Presentation() {}
const present = () => {
  cursor=0; effects=[];
  const tree=Page({presentation:Presentation}); effects.forEach(effect=>effect());
  return tree.props;
};
let typedOverride, historyOverride, stateOverride, actionOverride;
let capabilities, captures=0;
const originalFetch=fetchOverride;
const identity=(id)=>({recipient_id:id,app:'codex_desktop',task_id:'task-'+id,
  host_id:'host-a'});
let catalog=[
  {...identity('a'),title:'Duplicate',read_only:true,proven_control:'none',
    operations:['history','select'],send_agent_message:'unavailable'},
  {...identity('b'),title:'Duplicate',read_only:false,proven_control:'ui_bridge',
    operations:['history','send'],send_agent_message:'direct'},
];
sdk.prepareTask=async()=>({target_id:'chosen-task'});
fetchOverride=(url,body,options)=>{
  if(url.endsWith('/status')) return {configured:true,textInput:capabilities,
    taskContinuity:{supported:true}};
  if(url.endsWith('/native/attach')) {
    assert.equal(body.input_mode,'typed');assert.equal(body.surface,'dashboard');
    return {ok:true,input_mode:'typed',task:{target_id:body.target_id,
      tab_id:body.tab_id,connection_id:'typed-owner',generation:8}};
  }
  if(url.endsWith('/live/typed')) return typedOverride ? typedOverride(body) : {
    ok:true,operation_id:'operation-'+body.input_id,state:'admitted',pending:true};
  if(url.includes('/live/operation?')) return {ok:true,
    operation_id:decodeURIComponent(url.split('operation_id=')[1]),state:'completed',
    pending:false,result:{output:'Recorded reply'}};
  if(url.endsWith('/recipients/catalog')) return {ok:true,recipients:catalog,sources:[]};
  if(url.endsWith('/recipients/select')) {
    assert.equal(typeof body.action_id,'string');return {ok:true,recipient:body};
  }
  if(url.endsWith('/recipients/history')) return historyOverride ? historyOverride(body) : {
    ok:true,...body,messages:[{id:'m',role:'user',text:'visible'}]};
  if(url.endsWith('/state')) return stateOverride || {task:{},jobs:[],history:{messages:[]}};
  if(url.endsWith('/text/input')) return actionOverride ? actionOverride(body) : {
    ok:true,input_id:body.input_id,operation:body.operation,state:'accepted',
    recipient:body.recipient};
  return originalFetch(url,body,options);
};
const boot=async()=>{present();await drain();return present();};
const cleanup=()=>{for(const slot of slots)if(slot?.cleanup)slot.cleanup();};
"""


def execute(source_bundle, scenario):
    script = HARNESS + "\n(async()=>{\n" + scenario + r"""
cleanup();process.exit(0);
})().catch(error=>{console.error(error);process.exit(1);});
"""
    result = run(
        ["node", "-e", script, str(source_bundle)],
        capture_output=True, text=True, timeout=NODE_TIMEOUT_S,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_microphone_off_uses_actual_typed_contract_without_voice_start(source_bundle):
    execute(source_bundle, r"""
let props=await boot();const before=requests.length;
props.setTyped('  exact typed words\n');props=present();
assert.equal(requests.length,before);assert.equal(transports.length,0);
assert.equal(props.canSendTyped,true);await props.sendTyped();props=present();
const input=requests.find(row=>row.url.endsWith('/live/typed')).body;
assert.equal(input.text,'  exact typed words\n');assert.equal(input.admission,'async');
assert.equal(input.connection_id,'typed-owner');assert.equal(input.generation,8);
assert.equal(typeof input.provider_session_id,'string');
assert.equal(props.typed,'');assert.equal(transports.length,0);
assert.equal(props.active,false);assert.equal(props.transcript.at(-1).text,'Recorded reply');
assert(!requests.some(row=>row.url.endsWith('/session')||row.url.endsWith('/live/session')));
""")


def test_owner_message_through_text_input_settles_via_operation_polling(source_bundle):
    """With the explicit-operation descriptor present, an owner message rides /text/input;
    its async admission names an operation, and the panel settles it through the same
    /live/operation polling the provider-free typed path uses."""

    execute(source_bundle, r"""
capabilities={version:1,operations:['message','start_worker','steer','cancel','approval']};
actionOverride=body=>({ok:true,input_id:body.input_id,operation:body.operation,state:'queued',
  operation_id:'operation-'+body.input_id});
let props=await boot();props.setTyped('hello owner');props=present();
assert.equal(props.canSendTyped,true);await props.sendTyped();props=present();
const input=requests.find(row=>row.url.endsWith('/text/input')).body;
assert.equal(input.operation,'message');assert.equal(input.recipient,undefined);
assert(!requests.some(row=>row.url.endsWith('/live/typed')));
const polled=requests.find(row=>row.url.includes('/live/operation?'));
assert(polled,'the named operation must be polled');
assert(polled.url.includes('operation_id=operation-'+input.input_id));
assert.equal(props.typed,'');assert.equal(props.transcript.at(-1).text,'Recorded reply');
assert.equal(transports.length,0);
""")


def test_send_captures_once_and_keeps_new_draft_during_late_receipt(source_bundle):
    execute(source_bundle, r"""
let finish;typedOverride=body=>new Promise(resolve=>{finish=()=>resolve({ok:true,
  operation_id:'operation-'+body.input_id,state:'admitted',pending:true});});
let props=await boot();props.setTyped('first');props=present();
const pending=props.sendTyped();await waitFor(()=>finish);
props.sendTyped();present().setTyped('new words');finish();await pending;
assert.equal(present().typed,'new words');
assert.equal(requests.filter(row=>row.url.endsWith('/live/typed')).length,1);
assert.equal(requests.find(row=>row.url.endsWith('/live/typed')).body.text,'first');
""")


def test_uncertain_typed_admission_reuses_original_identity(source_bundle):
    execute(source_bundle, r"""
let count=0;typedOverride=body=>{if(++count===1)throw Error('network lost');
  return {ok:true,operation_id:'operation-'+body.input_id,state:'admitted',pending:true};};
let props=await boot();props.setTyped('keep original');await present().sendTyped();
assert.equal(present().typed,'keep original');assert(present().inputError);
await present().sendTyped();
const bodies=requests.filter(row=>row.url.endsWith('/live/typed')).map(row=>row.body);
assert.equal(bodies.length,2);assert.deepEqual(bodies[0],bodies[1]);
assert.equal(present().typed,'');assert.equal(transports.length,0);
""")


def test_files_remain_local_bounded_and_retained_until_upload_contract(source_bundle):
    execute(source_bundle, r"""
let props=await boot();props.setTyped('draft');
const file={name:'report.txt',size:12,type:'text/plain',slice(){}};
const before=requests.length;assert.equal(props.addAttachments([file]),true);
props=present();assert.equal(props.attachments[0].name,'report.txt');
assert.equal(props.canSendTyped,false);await props.sendTyped();
assert.equal(requests.length,before);assert.equal(props.typed,'draft');
assert.equal(props.addAttachments([{...file,size:11*1024*1024}]),false);
assert.equal(present().attachments.length,1);
props.removeAttachment(props.attachments[0].id);
assert.equal(present().canSendTyped,true);assert.equal(transports.length,0);
""")


def test_exact_read_only_selection_and_late_history_do_not_retarget(source_bundle):
    execute(source_bundle, r"""
let props=await boot();await props.refreshRecipients();props=present();
assert.equal(props.recipients.length,2);await props.setRecipient('a');props=present();
assert.equal(props.selectedRecipient,'a');assert.equal(props.canSendTyped,false);
let finish;historyOverride=body=>new Promise(resolve=>{finish=()=>resolve({ok:true,
  ...body,messages:[{role:'user',text:'old recipient'}]});});
const history=props.readRecipient();await waitFor(()=>finish);
await present().setRecipient('b');finish();await history;props=present();
assert.equal(props.selectedRecipient,'b');assert.equal(props.recipientHistory,null);
assert.equal(props.canSendTyped,false,'unimplemented dispatch must not gain send from read');
assert.equal(transports.length,0);
assert(!requests.some(row=>row.url.endsWith('/live/typed')||row.url.endsWith('/text/input')));
""")


def test_duplicate_recipient_ids_are_rejected_without_merging_permissions(source_bundle):
    execute(source_bundle, r"""
catalog=[catalog[0],{...catalog[1],recipient_id:'a'}];
await (await boot()).refreshRecipients();const props=present();
assert.equal(props.recipients.length,0);assert(props.recipientError.includes('ambiguous'));
assert.equal(transports.length,0);
""")


def test_selected_recipient_is_captured_on_explicit_dispatch(source_bundle):
    execute(source_bundle, r"""
capabilities={version:1,operations:['message','start_worker','steer','cancel','approval']};
await (await boot()).refreshRecipients();await present().setRecipient('b');
let finish;actionOverride=body=>new Promise(resolve=>{finish=()=>resolve({ok:true,
  input_id:body.input_id,operation:body.operation,state:'accepted',recipient:body.recipient});});
present().setTyped('for task b');let props=present();assert.equal(props.canSendTyped,true);
const sending=props.sendTyped();await waitFor(()=>finish);
await present().setRecipient('a');finish();await sending;
const input=requests.find(row=>row.url.endsWith('/text/input')).body;
assert.deepEqual(input.recipient,identity('b'));assert.equal(input.operation,'message');
assert.equal(present().selectedRecipient,'a');assert.equal(present().typed,'for task b');
assert.equal(present().actionReceipt,null);
""")


def test_stale_receipts_after_lifetime_end_do_not_clear_draft(source_bundle):
    execute(source_bundle, r"""
let finish;typedOverride=body=>new Promise(resolve=>{finish=()=>resolve({ok:true,
  operation_id:'operation-'+body.input_id,state:'admitted',pending:true});});
await boot();present().setTyped('retained');const pending=present().sendTyped();
await waitFor(()=>finish);listeners.pagehide();finish();await pending;
assert.equal(present().typed,'retained');assert.equal(present().actionReceipt,null);
assert.equal(transports.length,0);
""")


def test_approval_ids_choices_errors_and_repeat_action_identity(source_bundle):
    execute(source_bundle, r"""
capabilities={version:1,operations:['message','approval','cancel','steer']};
stateOverride={task:{},jobs:[{run_id:7,action_id:'job-action',status:'waiting_for_approval',
  approval:{actionable:true,approvals:[{request_id:'request-a',choices:['once','deny']}]}}]};
await (await boot()).refreshRecipients();let props=present();
const answer={run_id:7,action_id:'job-action',request_id:'request-a',choice:'once'};
await props.answerApproval({...answer,request_id:'stale'});
await props.answerApproval({...answer,choice:'session'});
assert.equal(requests.filter(row=>row.url.endsWith('/text/input')).length,0);
let count=0;actionOverride=body=>{if(++count===1)throw Error('approval unavailable');
  return {ok:true,input_id:body.input_id,operation:body.operation,state:'accepted'};};
await props.answerApproval(answer);assert(present().pendingActions['approval:request-a'].error);
await present().answerApproval(answer);
const bodies=requests.filter(row=>row.url.endsWith('/text/input')).map(row=>row.body);
assert.equal(bodies.length,2);assert.deepEqual(bodies[0],bodies[1]);
assert.equal(bodies[0].request_id,'request-a');assert.equal(bodies[0].action_id,'job-action');
assert.equal(bodies[0].choice,'once');
""")


def test_mute_sleep_wake_preserve_runtime_and_selected_mute(source_bundle):
    execute(source_bundle, r"""
startOverride=transport=>{const track={enabled:true};
  transport.media={getAudioTracks(){return [track];},getTracks(){return [{stop(){}}];}};
  transport.audio={muted:false,remove(){}};};
let props=await boot();await props.startTalk();props=present();
assert.equal(transports.length,1);const transport=transports[0];
props.setMuted(true);assert.equal(transport.media.getAudioTracks()[0].enabled,false);
props.setSleeping(true);assert.equal(transport.audio.muted,true);
props.setSleeping(false);assert.equal(transport.audio.muted,false);
assert.equal(transport.media.getAudioTracks()[0].enabled,false);
props.setMuted(false);assert.equal(transport.media.getAudioTracks()[0].enabled,true);
assert.equal(transports.length,1);assert.equal(transport.closed,false);
""")
