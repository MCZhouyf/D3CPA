from collections import defaultdict
from dc3pa.experiments.execution_schedule import MethodSpec,EvaluationUnit,build_schedule

def method(name):
    return MethodSpec(name,name,"profile","controller","frozen",name,
                      "commit",True,"ready-"+name)

def test_each_block_has_every_method():
    methods=[method("reactive"),method("fixed"),method("dc3pa")]
    units=[EvaluationUnit("task",str(i),"hard",f"b{i}") for i in range(9)]
    item=build_schedule(schedule_name="paper",blueprint_id="bp",
        source_commit="commit",model_profile_id="profile",
        methods=methods,units=units)
    blocks=defaultdict(list)
    for run in item.runs: blocks[run.block_id].append(run)
    assert all({x.method_id for x in rows}==
               {"reactive","fixed","dc3pa"} for rows in blocks.values())
    assert item.schedule_id==build_schedule(schedule_name="paper",
        blueprint_id="bp",source_commit="commit",
        model_profile_id="profile",methods=methods,units=units).schedule_id
