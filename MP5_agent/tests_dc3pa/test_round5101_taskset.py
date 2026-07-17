import csv,json
from dc3pa.experiments.taskset_canonicalization import (
 ActiveArtifactDescriptor,audit_active_taskset
)

def test_active_taskset_has_pressure_plate_and_no_sand(tmp_path):
 root=tmp_path/"active";root.mkdir()
 catalog=root/"catalog.csv"
 with catalog.open("w",newline="",encoding="utf-8") as f:
  w=csv.writer(f);w.writerow(["task","difficulty","minimum_subgoals"])
  difficulties=["basic","easy","medium","hard","complex"]
  index=0
  for d in difficulties:
   for j in range(10):
    task="craft wooden pressure plate" if index==0 else f"{d} task {j}"
    w.writerow([task,d,j+1]);index+=1
 (root/"design.json").write_text(json.dumps({"tasks":["craft wooden pressure plate"]}))
 audit=tmp_path/"audit.json"
 audit.write_text(json.dumps({"success_by_task":{"craft wooden pressure plate":4}}))
 report=audit_active_taskset(
  source_commit="commit",acquisition_source_commit="acq",
  active_root=root,catalog_path=catalog,
  descriptors=[ActiveArtifactDescriptor("design","design.json","design",True)],
  acquisition_audit_path=audit,
 )
 assert report.eligible
 assert report.old_task_total_occurrences==0
