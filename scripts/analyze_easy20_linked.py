"""Publish scripted calibration and source-preserving compressed game logs."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil

from memorybenchmark.prototypes.station_analysis import analyze_trace
from scripts.analyze_station_graphs import draw_graph


def read(path):return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    source=read(args.run/"report.json");report=read(args.run/"report.json")
    design=read(args.run/"design_snapshot.json")
    (args.output/"cases").mkdir()
    for case in report["witnesses"]:
        raw=args.run/case["log"];case["uncompressed_log_sha256"]=sha256(raw.read_bytes()).hexdigest()
        target=args.output/(case["log"]+".gz")
        target.write_bytes(gzip.compress(raw.read_bytes(),mtime=0))
        case["log"] += ".gz";case["log_encoding"]="gzip of authoritative UTF-8 JSON Lines; no fields removed"
        for field in ("graph","svg"):
            shutil.copy2(args.run/case[field],args.output/case[field])
    (args.output/"calibration.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family":"DejaVu Sans","font.size":10,"svg.fonttype":"none"}):
        fig,(ax,bar)=plt.subplots(1,2,figsize=(12,5))
        for key,label,color,style in (("baseline","Single-stage / short branches","#0072B2","--"),
                                      ("linked","Two-stage / longer branches","#D55E00","-")):
            data=source[key];values=sorted(100*(1-w['T3_T20']['retain']['operations']/w['T3_T20']['clear']['operations']) for w in data['per_world'])
            ax.step([0,*values,40],[0,*[(i+1)/len(values) for i in range(len(values))],1],where='post',label=label,color=color,linestyle=style)
        ax.set(xlim=(0,40),ylim=(0,1.02),xlabel="Reduction in T3-T20 operations (%)",ylabel="Fraction of enumerated worlds")
        ax.legend(frameon=False,fontsize=9,loc="lower right");ax.grid(alpha=.2)
        bottom=[0,0]
        for field,label,color in (("tasks_with_lower_retained_operations","Retain uses fewer ops","#0072B2"),
                                 ("tasks_with_equal_operations","Equal ops","#cccccc"),
                                 ("tasks_with_higher_retained_operations","Retain uses more ops","#D55E00")):
            heights=[source[k]['summary']['T3_T20'][field] for k in ('baseline','linked')]
            bar.bar([0,1],heights,bottom=bottom,color=color,label=label,width=.58)
            for i,h in enumerate(heights):bar.text(i,bottom[i]+h/2,f'{h:.1f}',ha='center',va='center',color='white' if field!='tasks_with_equal_operations' else 'black')
            bottom=[b+h for b,h in zip(bottom,heights)]
        bar.set(xticks=[0,1],xticklabels=['Single-stage','Two-stage'],ylim=(0,18),ylabel='Mean number of T3-T20 tasks')
        bar.legend(frameon=False,fontsize=9,loc='upper center',bbox_to_anchor=(.5,1.25))
        for a in (ax,bar):a.spines[['top','right']].set_visible(False)
        fig.suptitle('Environment calibration: the same feedback policy with and without history',x=.07,ha='left',fontsize=14)
        fig.text(.07,.025,'All 1,296 worlds per map; fixed scripted policy, not native agents or optimal information value.\nT1-T2 are ordinary scored tasks; T3-T20 are also shown separately. Zero and adverse task differences are retained.',fontsize=9)
        fig.subplots_adjust(left=.07,right=.98,bottom=.22,top=.76,wspace=.3)
        for suffix in ('png','svg','pdf'):fig.savefig(args.output/f'world-calibration.{suffix}',dpi=180,facecolor='white')
        plt.close(fig)
        for world in ('omega_0000','omega_5555'):
            fig,axes=plt.subplots(1,2,figsize=(14,9))
            for ax,condition in zip(axes,('retain','clear')):
                case=next(c for c in source['witnesses'] if c['world']==world and c['condition']==condition)
                graph=read(args.run/case['graph'])
                events=[json.loads(line) for line in (args.run/case['log']).read_text(encoding='utf-8').splitlines()]
                row=analyze_trace(design,events,graph['task_run_id'],exact_references=False)
                draw_graph(ax,design,graph,row,f'T3 / {condition} / {world}',focus_task=True)
            fig.suptitle('Fixed scripted witness: two complete stages in one task',x=.05,ha='left',fontsize=15)
            fig.text(.05,.905,'Predeclared family endpoints, not best-world selection. All worlds are included in calibration.',fontsize=10)
            fig.text(.05,.025,'Arrows are actual commutes; numbers show order. Dashed red routes contain unsupported processing.\nSmall unlabelled dots are real transit locations. No edge is inserted or removed. These are scripted traces, not agent results.',fontsize=9)
            fig.subplots_adjust(left=.05,right=.98,top=.86,bottom=.32,wspace=.18)
            for suffix in ('png','svg','pdf'):fig.savefig(args.output/f'{world}-t3.{suffix}',dpi=180,facecolor='white')
            plt.close(fig)
    manifest={'kind':'scripted_calibration_and_game_trace_export_not_agent_scores',
        'source_report_sha256':sha256((args.run/'report.json').read_bytes()).hexdigest(),
        'analysis_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'renderer_sha256':sha256(Path(__file__).with_name('analyze_station_graphs.py').read_bytes()).hexdigest(),
        'runtime_sources_sha256':{name:sha256(Path(name).read_bytes()).hexdigest() for name in (
            'memorybenchmark/prototypes/station_capability.py','memorybenchmark/prototypes/station_routes.py',
            'memorybenchmark/prototypes/station_choice.py','memorybenchmark/prototypes/station_analysis.py',
            'memorybenchmark/prototypes/station_session.py','scripts/build_easy20_linked_map.py',
            'scripts/check_easy20_linked.py')},
        'matplotlib_version':matplotlib.__version__,'png_dpi':180,
        'transforms':['exact finite-world ECDF; no smoothing','mean task counts across all worlds, including zeros and adverse differences',
                      'ordered multigraphs retain all actual moves and node actions','lossless gzip of full authoritative event logs'],
        'uncertainty':'No sampling intervals: these are exhaustive deterministic results for one fixed heuristic, not population agent performance.',
        'files_sha256':{p.relative_to(args.output).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.rglob('*')) if p.is_file()}}
    (args.output/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'figures':9,'compressed_logs':4}))


if __name__=='__main__':main()
