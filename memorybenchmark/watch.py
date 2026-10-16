"""Read-only experiment projections. Never serve raw native prompts or files."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    if path.stat().st_size > 12 * 1024**2:
        raise ValueError("record exceeds display budget")
    return json.loads(path.read_text(encoding="utf-8"))


def public_observation(observation):
    keys = ("task_id","task_name","instruction","location","conditions","world_time","revision",
            "neighbors","map","inventory","available_tools","stamina","initial_stamina","effort",
            "steps","max_steps","distance","done","success")
    return {k:deepcopy(observation[k]) for k in keys if k in observation}


def frame(response, action=None, source=None, at=None):
    observation=public_observation(response["observation"])
    target=observation["location"]["id"]
    return {"observation":observation,"feedback":response.get("feedback","")[:4000],
            "outcome":response.get("outcome"),"action":deepcopy(action),"source":source,
            "target":target,"moved":source is not None and source!=target,"at":at}


def memory_view(before,after=None,final=False):
    after=before if after is None else after
    changed=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k))
    return {"files":len(after),"bytes":sum(v.get("size",0) for v in after.values()),
            "changed":[p for p in changed if p!="file_access_stats.json"],"final":final}


def refresh_counts(data):
    latest={}
    for session in data["sessions"]:
        latest[(session["task_id"],session["condition"])]=session
    data["completed_sessions"]=sum(s["status"]=="complete" for s in latest.values())


def historical(root,report):
    data={"version":1,"id":root.name,"agent":report.get("agent","GenericAgent"),
          "model":report.get("model_alias",""),"kind":report.get("kind",""),
          "status":"complete" if report.get("complete") else "interrupted",
          "updated_at":None,"started_at":None,"tasks":report.get("tasks",[]),
          "total_sessions":report.get("prefix_count",1)+2*(len(report.get("tasks",[]))-report.get("prefix_count",1)),
          "completed_sessions":0,"active_session_id":None,"sessions":[],
          "failed_attempts":len(report.get("attempt_history",[])),"historical":True}
    rows=[("prefix",r) for r in report.get("prefix",[])]
    for pair in report.get("pairs",[]):
        for condition in pair.get("execution_order",("retain","clear")):
            row=pair.get("conditions",{}).get(condition)
            if row: rows.append((condition,row))
    for condition,row in rows:
        relative=str(row.get("path","")).replace("\\","/")
        directory=(root/relative).resolve()
        if root.resolve() not in directory.parents: continue
        session={"id":relative,"task_id":row["task_id"],"condition":condition,
                 "status":"complete" if row.get("infrastructure_ok") else "error",
                 "success":row.get("success"),"calls":row.get("llm_calls",0),
                 "phase":"finished","frames":[],"activity":[],
                 "memory":memory_view(row.get("input_memory",{}),row.get("output_memory"),True)}
        try:
            events_path=directory/"events.jsonl"
            if events_path.stat().st_size > 32*1024**2: continue
            events=[json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]
            run_id=next(e["task_run_id"] for e in reversed(events) if e["kind"]=="task_started")
            for event in events:
                if event["task_run_id"]!=run_id or "delivered" not in event: continue
                session["frames"].append(frame(event["delivered"],event.get("action"),event.get("from")))
        except (OSError,ValueError,StopIteration,KeyError):
            pass
        if session["frames"]:
            session["task_name"]=session["frames"][0]["observation"]["task_name"]
        data["sessions"].append(session)
    refresh_counts(data)
    return data


class Observer:
    def __init__(self,root):
        self.root=Path(root)
        self.path=self.root/"live.json"
        self.lock=threading.RLock()
        self.data=None

    def _write(self):
        self.data["updated_at"]=now()
        refresh_counts(self.data)
        # Telemetry failure must not change the agent/environment transaction.
        try: atomic_json(self.path,self.data)
        except OSError: pass

    def begin(self,report):
        with self.lock:
            try: self.data=read_json(self.path)
            except (OSError,ValueError): self.data=historical(self.root,report)
            self.data.update(status="running",historical=False)
            if not self.data.get("started_at"): self.data["started_at"]=now()
            self._write()

    def open(self,task,condition,response,before):
        with self.lock:
            sid=uuid4().hex
            self.data["sessions"].append({"id":sid,"task_id":task,"task_name":response["observation"]["task_name"],
                "condition":condition,"status":"running","success":None,"calls":0,"phase":"playing",
                "frames":[frame(response,at=now())],"activity":[],"memory":memory_view(before)})
            self.data["active_session_id"]=sid
            self._write()
            return sid

    def _session(self,sid):
        return next(s for s in self.data["sessions"] if s["id"]==sid)

    def activity(self,sid,kind,label,**fields):
        if sid is None: return
        with self.lock:
            session=self._session(sid)
            session.update(fields)
            session["activity"].append({"at":now(),"kind":kind,"label":label[:300]})
            session["activity"]=session["activity"][-120:]
            self._write()

    def observe(self,sid,response,action=None):
        if sid is None or "observation" not in response: return
        with self.lock:
            session=self._session(sid)
            previous=session["frames"][-1]
            if previous["observation"]["revision"]!=response["observation"]["revision"]:
                session["frames"].append(frame(response,action,previous["target"],now()))
                self._write()

    def memory(self,sid,before,after,final=False):
        if sid is None: return
        with self.lock:
            self._session(sid)["memory"]=memory_view(before,after,final)
            self._write()

    def close(self,sid,report):
        with self.lock:
            session=self._session(sid)
            session.update(status="complete" if report["infrastructure_ok"] else "error",
                           phase="finished",success=report["success"],calls=report["llm_calls"])
            if not report["infrastructure_ok"]:
                self.data["failed_attempts"]+=1
                session["activity"].append({"at":now(),"kind":"error","label":"本次运行中断，已保留检查点。"})
            self.data["active_session_id"]=None
            self._write()

    def finish(self,complete):
        with self.lock:
            self.data["status"]="complete" if complete else "interrupted"
            self.data["active_session_id"]=None
            self._write()


class WatchStore:
    def __init__(self,root):
        self.root=Path(root).resolve()

    def snapshot(self,run_id):
        if not isinstance(run_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",run_id):
            raise ValueError("无效的实验编号。")
        directory=self.root/run_id
        if directory.is_symlink() or getattr(directory,"is_junction",lambda:False)() or directory.resolve().parent!=self.root:
            raise ValueError("无效的实验目录。")
        if (directory/"live.json").exists():
            return read_json(directory/"live.json")
        return historical(directory,read_json(directory/"experiment.json"))

    def listing(self):
        if not self.root.exists(): return []
        directories=sorted((p for p in self.root.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime,reverse=True)
        result=[]
        for directory in directories:
            if len(result)>=50: break
            try:
                value=self.snapshot(directory.name)
                result.append({k:value.get(k) for k in ("id","model","agent","kind","status","updated_at",
                                                      "completed_sessions","total_sessions","active_session_id")})
            except (OSError,ValueError,KeyError,TypeError): continue
        return result
