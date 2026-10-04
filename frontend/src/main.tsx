import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {algorithmLabels,format,type Config,type Event,type Replay,type Scenario,type Snapshot} from './types';
import './style.css';
import {plannedEntries,movementEnd} from './timeline';

const palette=['#38cbb0','#67a4ff','#ffbd69','#c09bff','#ef839a','#66cfdf','#b2ce6d','#dca2cb'];
async function api<T>(url:string,body?:unknown):Promise<T>{
  const response=await fetch('/api'+url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
const defaults:Config={scenario:'intersection',fleet_size:4,algorithm:'periodic',demand:'saturated',seed:0,duration:120,warmup:0,delay_probability:.15,max_delay:3,slowdown_probability:.1,slowdown_factor:.6,timing_margin:.2,solver_budget:2,playback_speed:10};

function Arena({scenario,snapshot}:{scenario?:Scenario;snapshot?:Snapshot}){
  const ref=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{
    const canvas=ref.current;if(!canvas||!scenario)return;
    const draw=()=>{
      const dpr=window.devicePixelRatio||1,width=canvas.clientWidth,height=canvas.clientHeight;
      canvas.width=width*dpr;canvas.height=height*dpr;
      const ctx=canvas.getContext('2d')!;ctx.scale(dpr,dpr);
      const points=scenario.robots.flatMap(r=>r.legs.flat());
      const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
      const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
      const scale=Math.min((width-100)/(maxX-minX+2),(height-80)/(maxY-minY+2));
      const xy=(p:[number,number]):[number,number]=>[width/2+(p[0]-(minX+maxX)/2)*scale,height/2-(p[1]-(minY+maxY)/2)*scale];
      ctx.fillStyle='#101b24';ctx.fillRect(0,0,width,height);
      ctx.fillStyle='#24323e';for(let x=18;x<width;x+=24)for(let y=18;y<height;y+=24){ctx.beginPath();ctx.arc(x,y,1,0,Math.PI*2);ctx.fill();}
      for(const [i,r] of scenario.robots.entries()){
        const moving=snapshot?.robots.find(robot=>robot.id===r.id)?.moving;
        ctx.lineWidth=moving?3:1.5;ctx.strokeStyle=palette[i%palette.length]+(moving?'95':'45');ctx.setLineDash([5,7]);
        for(const leg of r.legs){ctx.beginPath();leg.forEach((p,j)=>{const [x,y]=xy(p);if(j)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();}
        ctx.setLineDash([]);
        for(const leg of r.legs){const [x,y]=xy(leg[0]);ctx.strokeStyle='#6b7e8a';ctx.lineWidth=1;ctx.strokeRect(x-7,y-7,14,14);}
      }
      for(const [i,r] of scenario.robots.entries()){
        const state=snapshot?.robots.find(robot=>robot.id===r.id);const [x,y]=xy(state?.position||r.legs[0][0]);
        const radius=Math.max(5,r.radius*scale);
        ctx.beginPath();ctx.arc(x,y,radius+5,0,Math.PI*2);ctx.fillStyle=palette[i%palette.length]+'18';ctx.fill();
        ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.fillStyle=palette[i%palette.length];ctx.fill();
        ctx.strokeStyle='#e3f8f1';ctx.lineWidth=1.5;ctx.stroke();
        ctx.font='11px ui-monospace,monospace';ctx.fillStyle='#d0dce2';ctx.fillText(r.id,x+radius+6,y-7);
      }
      ctx.font='11px ui-monospace,monospace';ctx.fillStyle='#778e9c';ctx.fillText('METERS · FIXED ROUTES · PRIVATE WAITING BAYS',20,height-18);
    };
    draw();const observer=new ResizeObserver(draw);observer.observe(canvas);return()=>observer.disconnect();
  },[scenario,snapshot]);
  return <canvas ref={ref} aria-label="Robot movement simulation"/>;
}

function Timeline({scenario,snapshot,events}:{scenario?:Scenario;snapshot?:Snapshot;events:Event[]}){
  const now=snapshot?.time||0,start=Math.max(0,now-30),end=start+60;
  return <div className="timeline"><div className="timeline-scale"><span>{format(start,0)}s</span><span>{format(start+30,0)}s</span><span>{format(end,0)}s</span></div>{scenario?.robots.map((r,i)=>{
    const period=snapshot?.plan?.period;
    const planned=snapshot?.config?.algorithm==='periodic'?plannedEntries(snapshot?.plan?.starts[r.id]||[],period,start,end):[];
    return <div className="timeline-row" key={r.id}><span>{r.id}</span><div className="track"><div className="now" style={{left:`${(now-start)/60*100}%`}}/>{planned.map((t,j)=><i key={j} className="planned" title={`Scheduled entry ${format(t)} s`} style={{left:`${(t-start)/60*100}%`}}/>)}{events.filter(e=>e.type==='movement_start'&&e.robot===r.id&&(e.end||0)>start&&(e.start||0)<end).map((e,j)=>{
      const finish=movementEnd(e,events);
      const left=Math.max(start,e.start||0),right=Math.min(end,finish);
      return <div key={j} title={`${r.id} leg ${e.leg}: ${format(e.start)}–${format(finish)} s`} className="movement" style={{left:`${(left-start)/60*100}%`,width:`${Math.max(0,(right-left)/60*100)}%`,background:palette[i%palette.length]}}/>;
    })}</div></div>;
  })}</div>;
}

function App(){
  const [config,setConfig]=useState(defaults),[scenario,setScenario]=useState<Scenario>(),[snapshot,setSnapshot]=useState<Snapshot>(),[runList,setRunList]=useState<Snapshot[]>([]),[events,setEvents]=useState<Event[]>([]),[error,setError]=useState(''),[starting,setStarting]=useState(false),[tab,setTab]=useState('arena'),[replay,setReplay]=useState<Replay>(),[frame,setFrame]=useState(0),[replayPlaying,setReplayPlaying]=useState(false),[robot,setRobot]=useState('r00');
  const socket=useRef<WebSocket|null>(null);
  const shown=replay?{...replay.frames[frame],config:replay.header.data.config}:snapshot;
  const shownScenario=replay?.header.data.scenario||snapshot?.scenario||scenario;
  const active=snapshot&&['starting','running'].includes(snapshot.status);
  const loadRuns=()=>api<Snapshot[]>('/runs').then(setRunList).catch(e=>setError(e.message));
  useEffect(()=>{api<Scenario[]>(`/scenarios?fleet_size=${config.fleet_size}`).then(items=>setScenario(items.find(s=>s.name===config.scenario))).catch(e=>setError(e.message));},[config.scenario,config.fleet_size]);
  useEffect(()=>{loadRuns();const timer=setInterval(loadRuns,3000);return()=>{clearInterval(timer);socket.current?.close();};},[]);
  useEffect(()=>{if(!replayPlaying||!replay)return;const timer=setInterval(()=>setFrame(n=>{if(n>=replay.frames.length-1){setReplayPlaying(false);return n;}return n+1;}),100);return()=>clearInterval(timer);},[replayPlaying,replay]);
  function connect(run:Snapshot){
    socket.current?.close();setSnapshot(run);setReplay(undefined);setReplayPlaying(false);setEvents([]);setError('');
    if(['starting','running'].includes(run.status)){
      const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/runs/${run.id}/stream`);socket.current=ws;
      ws.onmessage=message=>{const update=JSON.parse(message.data) as Snapshot;setSnapshot(prev=>({...prev,...update,config:run.config,scenario:run.scenario}));setEvents(prev=>{const all=[...prev,...(update.events||[])];const unique=new Map(all.map(event=>[JSON.stringify(event),event]));return [...unique.values()];});};
      ws.onerror=()=>setError('Live connection interrupted. Select the run again to reconnect.');
    }
  }
  async function start(){setStarting(true);setError('');try{connect(await api<Snapshot>('/runs',config));setTab('arena');await loadRuns();}catch(e){setError((e as Error).message);}finally{setStarting(false);}}
  async function command(type:string){if(!snapshot)return;try{await api(`/runs/${snapshot.id}/control`,{type,robot,seconds:3});}catch(e){setError((e as Error).message);}}
  async function openReplay(run:Snapshot){try{const record=await api<Replay>(`/runs/${run.id}/replay`);socket.current?.close();setSnapshot(run);setReplay(record);setFrame(0);setEvents(record.events);setTab('arena');setReplayPlaying(false);setError('');}catch(e){setError((e as Error).message);}}
  const update=(key:keyof Config,value:string|number)=>setConfig(c=>({...c,[key]:value,custom_scenario:null}));
  const numberInput=(label:string,key:keyof Config,min:number,max:number,step=1)=><label>{label}<input type="number" min={min} max={max} step={step} value={config[key] as number} onChange={e=>update(key,e.target.valueAsNumber)}/></label>;
  const visibleEvents=replay?events.filter(e=>e.time<=(shown?.time||0)):events;
  return <div className="shell">
    <header><div className="brand"><div className="brand-mark">AP</div><div><strong>Fleet Lab</strong><small>PERIODIC ROBOT COORDINATION</small></div></div><div className="header-right"><span className="tag">RESEARCH WORKBENCH</span><a href="https://github.com/nikhil-m-v/ap-fleet-lab" target="_blank" rel="noreferrer">Source ↗</a></div></header>
    <div className="layout"><aside>
      <div className="eyebrow">EXPERIMENT SETUP</div><h1>Find the rhythm.</h1><p className="intro">Compare repeating schedules with reactive robot coordination.</p>
      <label>Environment<select value={config.scenario} onChange={e=>update('scenario',e.target.value)}><option value="intersection">Shared intersection</option><option value="corridor">Opposing corridor</option><option value="warehouse">Warehouse workcells</option></select></label>
      <label>Scheduling strategy<select value={config.algorithm} onChange={e=>update('algorithm',e.target.value)}>{Object.entries(algorithmLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <div className="two">{numberInput('Robots','fleet_size',2,32)}{numberInput('Random seed','seed',0,2147483647)}</div>
      <label>Mission demand<select value={config.demand} onChange={e=>update('demand',e.target.value)}><option value="saturated">Always ready</option><option value="intermittent">Intermittent arrivals</option><option value="bursts">Bursts every 30 seconds</option></select></label>
      <div className="two">{numberInput('Measure, seconds','duration',1,3600)}{numberInput('Warm-up, seconds','warmup',0,3600)}</div>
      <label className="range-label">Stop probability <b>{Math.round(config.delay_probability*100)}%</b><input type="range" min="0" max="1" step=".05" value={config.delay_probability} onChange={e=>update('delay_probability',+e.target.value)}/></label>
      <div className="two">{numberInput('Max stop, seconds','max_delay',0,60,.5)}{numberInput('Timing margin, s','timing_margin',0,10,.1)}</div>
      <details><summary>Advanced settings</summary><div className="two">{numberInput('Solver budget, s','solver_budget',0,30,.1)}{numberInput('Playback speed','playback_speed',1,100)}</div><div className="two">{numberInput('Slowdown chance','slowdown_probability',0,1,.05)}{numberInput('Speed multiplier','slowdown_factor',.1,1,.05)}</div><label className="upload">Load scenario JSON<input type="file" accept="application/json,.json" onChange={async e=>{try{const file=e.target.files?.[0];if(!file)return;const s=JSON.parse(await file.text()) as Scenario;await api('/scenarios/validate',s);setConfig(c=>({...c,custom_scenario:s}));setScenario(s);setError('');}catch(err){setError((err as Error).message);}}}/></label>{config.custom_scenario&&<small>Custom geometry: {config.custom_scenario.name}</small>}</details>
      <button className="primary" onClick={start} disabled={starting||!!active}>{starting?'Preparing experiment…':active?'Experiment in progress':'Run experiment →'}</button>
      <p className="hint">Changing settings applies to the next run. Movement permissions stay held until actual completion.</p>
      <div className="formula"><span>THE AP SCHEDULE</span><div>tᵢ,ⱼ,ₙ = φᵢ + δᵢ,ⱼ + nT</div><small>Optimize the period. Verify every movement.</small></div>
    </aside><main>
      {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')}>×</button></div>}
      <div className="workspace-top"><nav><button className={tab==='arena'?'selected':''} onClick={()=>setTab('arena')}>Simulation</button><button className={tab==='compare'?'selected':''} onClick={()=>setTab('compare')}>Compare runs <span>{runList.length}</span></button></nav><div className="status"><i className={shown?.status==='running'&&!shown.paused?'live':''}/>{replay?'REPLAY':shown?.paused?'PAUSED':shown?.status?.replace('_',' ').toUpperCase()||'READY'}</div></div>
      {tab==='arena'?<>
        <section className="arena-panel"><div className="panel-heading"><div><span className="eyebrow">{shownScenario?.name.replace('_',' ').toUpperCase()||'ENVIRONMENT'}</span><h2>{algorithmLabels[snapshot?.config?.algorithm||config.algorithm]}</h2></div><div className="clock">{format(shown?.time||0)}<small>SIM SECONDS</small></div></div><Arena scenario={shownScenario} snapshot={shown}/><div className="arena-footer"><div><span className="legend-dot"/> Robot & route <span className="bay-symbol"/> Private waiting bay</div><div>{shownScenario?.robots.length||config.fleet_size} robots · continuous 2D</div></div></section>
        <div className="run-controls">{replay?<><button onClick={()=>setReplayPlaying(!replayPlaying)}>{replayPlaying?'Pause replay':'Play replay'}</button><input aria-label="Replay frame" type="range" min="0" max={replay.frames.length-1} value={frame} onChange={e=>setFrame(+e.target.value)}/><span>{frame+1}/{replay.frames.length}</span><button onClick={()=>{setReplay(undefined);setReplayPlaying(false);}}>Exit replay</button></>:<><button disabled={!active} onClick={()=>command(snapshot?.paused?'resume':'pause')}>{snapshot?.paused?'Resume':'Pause'}</button><button disabled={!active} onClick={()=>command('stop')}>End run</button><div className="spacer"/><select aria-label="Robot to disrupt" value={robot} onChange={e=>setRobot(e.target.value)}>{shownScenario?.robots.map(r=><option key={r.id}>{r.id}</option>)}</select><button disabled={!active} onClick={()=>command('disrupt')}>Inject 3s stop</button></>}</div>
        <div className="metrics">{[['THROUGHPUT',format(shown?.metrics.missions_per_minute),'missions / min'],['P95 WAIT',format(shown?.metrics.p95_wait_seconds),'seconds at bays'],['FAIRNESS',format(shown?.metrics.jain_fairness,2),'Jain index · 1 is equal'],['CLEARANCE VIOLATIONS',String(shown?.metrics.clearance_violations||0),'continuous checks']].map(([label,value,unit])=><div className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>)}</div>
        <section className="light-panel"><div className="section-title"><h3>Movement timeline</h3><span>Bars: actual occupancy · dashed marks: AP entries</span></div><Timeline scenario={shownScenario} snapshot={shown} events={visibleEvents}/></section>
        <div className="bottom-grid"><section className="light-panel"><div className="section-title"><h3>Planner diagnostics</h3><span>{shown?.plan?.status||'Awaiting run'}</span></div><dl><dt>Common period</dt><dd>{format(shown?.plan?.period)} s</dd><dt>Period lower bound</dt><dd>{format(shown?.plan?.lower_bound)} s</dd><dt>Optimality gap</dt><dd>{shown?.plan?.optimality_gap==null?'—':format(shown.plan.optimality_gap*100)+'%'}</dd><dt>Total planning time</dt><dd>{format(shown?.metrics.planning_seconds,3)} s</dd><dt>Queued missions</dt><dd>{shown?.metrics.queue_size||0}</dd><dt>Schedule version</dt><dd>{shown?.schedule_version||'—'}</dd></dl>{shown?.error&&<p className="error-text">{shown.error}</p>}</section><section className="light-panel"><div className="section-title"><h3>Event log</h3><span>{visibleEvents.length} events</span></div><div className="event-log">{visibleEvents.filter(e=>e.type!=='plan').slice(-15).reverse().map((e,i)=><div key={i}><time>{format(e.time)}s</time><span>{e.type.replaceAll('_',' ')}</span><b>{e.robot||'fleet'}</b></div>)}{!visibleEvents.length&&<p>Start a run to inspect admissions, delays, and completions.</p>}</div></section></div>
      </>:<section className="light-panel comparison"><div className="section-title"><h3>Experiment history</h3><button onClick={loadRuns}>Refresh</button></div><p>Compare runs with matching environments, demand, seeds, and measurement windows. Small samples are exploratory.</p><div className="table-scroll"><table><thead><tr><th>Strategy / environment</th><th>Seed</th><th>State</th><th>Missions/min</th><th>P95 wait</th><th>Fairness</th><th>Actions</th></tr></thead><tbody>{runList.map(run=><tr key={run.id}><td><strong>{algorithmLabels[run.config?.algorithm||'']}</strong><small>{run.config?.scenario} · {run.config?.fleet_size} robots · {run.config?.demand} · {run.config?.duration}s + {run.config?.warmup}s warm-up</small></td><td>{run.config?.seed}</td><td>{run.status}</td><td>{format(run.metrics.missions_per_minute)}</td><td>{format(run.metrics.p95_wait_seconds)}s</td><td>{format(run.metrics.jain_fairness,2)}</td><td><div className="table-actions">{['starting','running'].includes(run.status)?<button onClick={()=>{connect(run);setTab('arena');}}>Open</button>:<><button onClick={()=>openReplay(run)}>Replay</button><a href={`/api/runs/${run.id}/export`}>Export</a></>}</div></td></tr>)}</tbody></table></div>{!runList.length&&<div className="empty">Your experiments will appear here.</div>}</section>}
      <footer>AP Fleet Lab · v0.1 <span>Fixed routes. Conservative traversal reservations. Research simulation.</span></footer>
    </main></div>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
