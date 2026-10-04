import type {Event} from './types';
export function plannedEntries(offsets:number[],period:number|undefined|null,start:number,end:number){
  if(!period||period<=0)return [];
  const entries:number[]=[];
  for(const offset of offsets){
    for(let n=Math.max(0,Math.ceil((start-offset)/period));offset+n*period<end;n++)entries.push(offset+n*period);
  }
  return entries.sort((a,b)=>a-b);
}
export function movementEnd(event:Event,events:Event[]){
  const actual=events.find(e=>e.type==='movement_end'&&e.robot===event.robot&&e.leg===event.leg&&e.mission===event.mission);
  if(actual)return actual.time;
  const next=events.find(e=>e.type==='movement_start'&&e.robot===event.robot&&(e.start||0)>(event.start||0));
  const extra=events.filter(e=>e.type==='manual_disruption'&&e.robot===event.robot&&e.time>=(event.start||0)&&e.time<(next?.start||Infinity)).reduce((sum,e)=>sum+(e.seconds||0),0);
  return (event.end||0)+extra;
}
