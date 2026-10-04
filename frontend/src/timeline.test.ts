import {describe,it,expect} from 'vitest';
import {plannedEntries,movementEnd} from './timeline';
import type {Event} from './types';
describe('timeline fidelity',()=>{
  it('includes an offset crossing the common cycle boundary without negative repetitions',()=>{
    expect(plannedEntries([8,12],10,10,30)).toEqual([12,18,22,28]);
    expect(plannedEntries([8],10,0,10)).toEqual([8]);
    expect(plannedEntries([8],null,0,10)).toEqual([]);
  });
  it('uses actual clearance time instead of predicted release',()=>{
    const start:Event={time:0,type:'movement_start',robot:'r00',mission:0,leg:0,start:0,end:10};
    const stop:Event={time:5,type:'manual_disruption',robot:'r00',seconds:8};
    expect(movementEnd(start,[start,stop])).toBe(18);
    expect(movementEnd(start,[start,stop,{time:20,type:'movement_end',robot:'r00',mission:0,leg:0}])).toBe(20);
  });
  it('counts chained stops after the initial predicted end but excludes later missions',()=>{
    const start:Event={time:0,type:'movement_start',robot:'r00',mission:0,leg:0,start:0,end:10};
    const events:Event[]=[start,{time:5,type:'manual_disruption',robot:'r00',seconds:8},{time:12,type:'manual_disruption',robot:'r00',seconds:3},{time:25,type:'movement_start',robot:'r00',mission:1,leg:0,start:25,end:35},{time:30,type:'manual_disruption',robot:'r00',seconds:4}];
    expect(movementEnd(start,events)).toBe(21);
  });
});
