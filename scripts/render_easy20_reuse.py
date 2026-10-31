"""Export a complete source-backed geography and twenty-commission overview."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import load_design, map_world
from memorybenchmark.prototypes.station_experience import experience_schedule
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN


COLORS = {"NS": "#186580", "EW": "#975222"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--world", help="optional assertion of the map's fixed assignment")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    design = load_design(EASY20_REUSE_DESIGN)
    args.world = map_world(design, args.world)
    assignment = design["private_worlds"][args.world]
    public, rows = design["public"], experience_schedule(design)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.font_manager import FontProperties, fontManager

    installed = {f.name for f in fontManager.ttflist}
    family = next((n for n in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "Arial Unicode MS") if n in installed), None)
    if family is None:
        raise RuntimeError("A CJK font is required for this Chinese design overview")
    source_rows = []
    for row in rows:
        for stage in row["stages"]:
            source_rows.append({"task_id": row["task_id"], "stage": stage["stage_index"] + 1,
                "target": stage["target"], "kind": stage["required_kind"],
                "earlier_same_kind_stages": ";".join(f"{s['task_id']}.{s['stage_index']+1}" for s in stage["earlier_same_kind_stages"]),
                "intervening_requirements": stage["intervening_tasks_since_same_kind_requirement"],
                "exact_repeat_of": row["exact_repeat_of"] or ""})
    with (args.output / "task-dependencies.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source_rows[0])); writer.writeheader(); writer.writerows(source_rows)
    (args.output / "task-dependencies.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    groups = public["capability_groups"]
    group_of = {s: key for key, group in groups.items() for s in group["stations"]}
    group_of.update(dict(zip(("P", "Q", "R", "S", "U", "V", "X", "Y"), ("NS", "NS", "EW", "EW", "NS", "NS", "EW", "EW"))))
    files = []
    with plt.rc_context({"font.family": family, "font.size": 11, "axes.unicode_minus": False,
                         "svg.fonttype": "path", "pdf.fonttype": 42}):
        fig = plt.figure(figsize=(18, 12), facecolor="#f7f6ef")
        fig.text(.045, .945, "岚汀丘地 · Easy 20 完整地图", fontsize=25, weight="bold", color="#243e36")
        fig.text(.045, .912, "v5 同型联程  /  8 种公开站型 · 每型两站 · 70 个地点 · 77 条道路 · 8 个采集点", fontsize=12, color="#4e625a")
        ax = fig.add_axes((.035, .095, .705, .79)); ax.set_aspect("equal")
        ax.set(xlim=(120, 1850), ylim=(1660, 90)); ax.axis("off")
        places = public["locations"]
        for a, b, weight in public["edges"]:
            x1, y1, x2, y2 = places[a]["x"], places[a]["y"], places[b]["x"], places[b]["y"]
            ax.plot([x1, x2], [y1, y2], color="#72877d", linewidth=1.3, zorder=1)
            dx, dy = x2-x1, y2-y1; length = max(1, (dx*dx+dy*dy)**.5)
            ax.text((x1+x2)/2-dy/length*10, (y1+y2)/2+dx/length*10, str(weight), fontsize=7,
                    color="#425b50", ha="center", va="center", zorder=2,
                    bbox={"facecolor": "#f7f6ef", "edgecolor": "none", "pad": .5})
        for id_, place in places.items():
            x, y = place["x"], place["y"]; kind = place["kind"]
            color = COLORS.get(group_of.get(id_), "#42594e")
            if place.get("transit"):
                ax.scatter(x, y, s=13, color="#7d8f85", zorder=3)
                ax.annotate(id_, (x, y), xytext=(5, 5), textcoords="offset points", fontsize=6.3, color="#5a6f63")
            elif kind == "station":
                ax.scatter(x, y, s=150, marker="s", facecolor="#f7f6ef", edgecolor=color, linewidth=1.9, zorder=4)
                ax.annotate(id_, (x, y), xytext=(0, -2), textcoords="offset points", ha="center", va="center", fontsize=8, color=color, weight="bold",zorder=6)
            elif kind == "survey":
                ax.scatter(x, y, s=220, marker="o", facecolor=color, edgecolor="#f7f6ef", linewidth=1.4, zorder=4)
                ax.annotate(id_, (x, y), xytext=(0, -1), textcoords="offset points", ha="center", va="center", fontsize=10, color="white", weight="bold",zorder=6)
            elif kind == "camp":
                ax.scatter(x, y, s=220, marker="^", color="#243e36", zorder=4)
                ax.annotate("C · 手记营地", (x, y), xytext=(15, -2), textcoords="offset points", fontsize=12, color="#243e36")
            else:
                ax.scatter(x, y, s=45, facecolor="#f7f6ef", edgecolor="#637b6d", linewidth=1.3, zorder=3)
                ax.annotate(id_, (x, y), xytext=(-8, -13), textcoords="offset points", fontsize=9, color="#42594e")
        handles = [Line2D([], [], marker=m, linestyle="None", markersize=s, markerfacecolor=c, markeredgecolor="#42594e", label=label)
                   for m, s, c, label in (("^", 9, "#243e36", "营地：出发 / 最终交件"), ("o", 9, "#186580", "采集点：到达自动采集"),
                                          ("s", 8, "#f7f6ef", "基站：主动查询 / 处理"), (".", 5, "#7d8f85", "中间地点：必须逐点移动"))]
        ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(.015, -.035), frameon=False, fontsize=10, ncol=2)
        for index, (key, group) in enumerate(groups.items()):
            y = .825-index*.32; color = COLORS[key]
            fig.text(.765, y, group["name"], fontsize=15, weight="bold", color=color)
            for k,type_id in enumerate(group["station_types"]):
                fig.text(.765,y-.043-k*.034,f"{type_id} 型："+" / ".join(public["station_types"][type_id]["stations"]),fontsize=12,color="#243e36")
            names=[public["kinds"][k].replace("资料","") for k in group["kinds"]]
            fig.text(.765,y-.195,"候选功能："+" / ".join(names[:2])+"\n　　　　　"+" / ".join(names[2:]),fontsize=10,linespacing=1.8,color="#4e625a")
        fig.text(.765, .135, "公开地图只标站型与地理。\n每型两站功能完全相同。\n具体处理能力需现场获知；\n类型与能力的配对轮内固定。", fontsize=10, linespacing=1.8, color="#4e625a")
        fig.text(.045, .04, "所有委托：C 出发 → 第 1 段采集并在匹配站处理 → 第 2 段采集并处理 → C 交件。\n布局为示意；边旁数字为道路距离。本图不含隐藏能力配对，不会将历史反馈随地图传给 Agent。", fontsize=10, linespacing=1.7, color="#4e625a")
        for suffix in ("png", "svg", "pdf"):
            file = args.output / f"complete-map.{suffix}"; fig.savefig(file, dpi=180, facecolor=fig.get_facecolor()); files.append(file)
        plt.close(fig)

        fig = plt.figure(figsize=(18, 13), facecolor="#f7f6ef")
        fig.text(.045, .947, "二十项委托 · 经验承接表", fontsize=25, weight="bold", color="#243e36")
        fig.text(.045, .913, "40 段行程中，32 段有更早的同类处理需求；前序成功处理可确认一种站型及它在两地的站。", fontsize=12, color="#4e625a")
        ax = fig.add_axes((.045, .16, .91, .72)); ax.axis("off")
        cells = []
        for row in rows:
            values = [row["task_id"]]
            for stage in row["stages"]:
                values.append(f"{stage['target']} · {public['kinds'][stage['required_kind']]}")
                sources = stage["earlier_same_kind_stages"]
                values.append(f"{sources[-1]['task_id']}.{sources[-1]['stage_index']+1} 成功后可用" if sources else "首次需求 · 可自主探索")
            values.append(f"重复 {row['exact_repeat_of']}" if row["exact_repeat_of"] else "—")
            cells.append(values)
        table = ax.table(cellText=cells, colLabels=["委托", "第 1 段采集 / 处理", "最近同类需求", "第 2 段采集 / 处理", "最近同类需求", "整项重复"],
                         colWidths=[.07, .22, .20, .22, .20, .09], bbox=(0, 0, 1, 1), cellLoc="left")
        table.auto_set_font_size(False); table.set_fontsize(10)
        for (r, c), cell in table.get_celld().items():
            cell.set_edgecolor("#d7dfd5"); cell.set_linewidth(.5)
            cell.set_facecolor("#dce6db" if r == 0 else "#ffffff" if r % 2 else "#edf1e9")
            cell.get_text().set_color("#243e36"); cell.PAD=.12
            if r == 0: cell.get_text().set_weight("bold")
        fig.text(.045, .111, "每项均从 C 出发、完成两段后回 C 交件；任务只给资料与采集点，不指定处理站。", fontsize=12, color="#243e36")
        fig.text(.045, .06, "表内列最近的同类需求；任一更早同类成功处理均可提供经验。若前序未成功，仅按实际反馈判断机会。\n首次需求不等于没有经验：此前的失败试探或可选查询也可能已经揭示匹配站。间隔不等于无复习保持时长。\n这是固定任务设计与条件依赖，不是 Agent 已保存或使用记忆的证明；原生 Agent 的新版实验尚未运行。", fontsize=10, linespacing=1.8, color="#4e625a")
        for suffix in ("png", "svg", "pdf"):
            file = args.output / f"twenty-task-dependencies.{suffix}"; fig.savefig(file, dpi=180, facecolor=fig.get_facecolor()); files.append(file)
        plt.close(fig)
        fig=plt.figure(figsize=(12,9),facecolor="#f7f6ef")
        fig.text(.07,.91,"站型与能力 · 隐藏配对示例",fontsize=23,weight="bold",color="#243e36")
        fig.text(.07,.865,f"仅供人类设计检查，示例世界 {args.world}；以下配对不出现在公开地图或任务要求中。",fontsize=11,color="#4e625a")
        ax=fig.add_axes((.07,.30,.86,.50));ax.axis("off")
        mapping=[[f"{t} 型"," / ".join(data["stations"]),public["kinds"][assignment[data["stations"][0]]]] for t,data in public["station_types"].items()]
        table=ax.table(cellText=mapping,colLabels=["公开站型","公开地点","隐藏处理能力"],cellLoc="left",bbox=(0,0,1,1))
        table.auto_set_font_size(False);table.set_fontsize(13)
        for (r,c),cell in table.get_celld().items():
            cell.set_edgecolor("#d7dfd5");cell.set_linewidth(.6);cell.set_facecolor("#dce6db" if r==0 else "white" if r%2 else "#edf1e9");cell.PAD=.15
        sample=next(t for t,data in public["station_types"].items() if assignment[data["stations"][0]]=="profile")
        fig.text(.07,.215,f"交互获得：在 {sample}1 处理剖面成功 → 自主保存“{sample} 型支持剖面”。",fontsize=13,color="#243e36")
        fig.text(.07,.16,f"跨地点复用：后续在另一处采集剖面 → 可选择此前没到过的 {sample}2。",fontsize=13,color="#243e36")
        fig.text(.07,.075,"同型一致是公开规则，具体配对由交互获知。选择同型站是行为证据，不单独证明内部记忆使用。\n这张图展示规则和条件关系，不是 Agent 的实际执行结果。",fontsize=10,linespacing=1.8,color="#4e625a")
        for suffix in ("png","svg","pdf"):
            file=args.output/f"station-type-example.{suffix}";fig.savefig(file,dpi=180,facecolor=fig.get_facecolor());files.append(file)
        plt.close(fig)
    for file in files:
        if file.suffix == ".svg":
            file.write_text("\n".join(line.rstrip() for line in file.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8")
    manifest = {"kind": "complete_design_overview_not_agent_results", "design_id": design["design_id"],
                "design_sha256": sha256(EASY20_REUSE_DESIGN.read_bytes()).hexdigest(),
                "renderer_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "example_world": args.world, "example_capabilities": assignment,
                "nodes": len(public["locations"]), "roads": len(public["edges"]),
                "font": family, "matplotlib": matplotlib.__version__, "png_dpi": 180,
                "transformations": ["All source nodes, roads, distances, and twenty commissions retained.",
                    "Coordinates are a schematic layout, not geographic distance.",
                    "Task table displays the most recent same-kind demand; machine-readable JSON/CSV retain all predecessors.",
                    "Example capabilities are evaluator-only; no agent memories created."],
                "files_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in files}}
    (args.output / "figure-provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "figures": len(files), "nodes": len(public["locations"]), "roads": len(public["edges"])}))


if __name__ == "__main__":
    main()
