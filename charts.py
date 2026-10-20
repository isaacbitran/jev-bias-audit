"""Write chart CSVs from results/ and render PNGs into charts/. Usage: python3 -I charts.py"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES, OUT = os.path.join(HERE, "results"), os.path.join(HERE, "charts")
os.makedirs(OUT, exist_ok=True)
BLUE, ORANGE, GRAY, INK, INK2 = "#2a78d6", "#eb6834", "#b5b3ad", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRAY, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb"})


def rd(name):
    return list(csv.DictReader(open(os.path.join(RES, name))))


def wr(name, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


S = rd("single_effects.csv")

# 1. Within-attribute contrasts, pooled over all signed decision tasks (forest plot, both models)
keep = [("republican", "democrat"), ("black", "white"), ("hispanic", "white"), ("asian", "white"),
        ("native_american", "white"), ("middle_eastern", "white"), ("muslim", "christian"), ("jewish", "christian"),
        ("atheist", "christian"), ("woman", "man"), ("nonbinary", "man"), ("gay", "straight"), ("bisexual", "straight"),
        ("undocumented", "us_born_citizen"), ("refugee", "us_born_citizen"), ("age22", "age45"), ("age70", "age45")]
rows = []
for g, ref in keep:
    for m in ("jev-1.13.0", "jev-1.14.0"):
        r = next(x for x in S if x["model"] == m and x["comparison"] == "label_vs_ref" and x["group"] == g and x["domain"] == "ALL_SIGNED")
        rows.append(dict(contrast=f"{g} vs {ref}", model=m, mean_pp=r["mean_pp"], ci_lo_pp=r["ci_lo_pp"], ci_hi_pp=r["ci_hi_pp"],
                         q_bh=r["q_bh"], passes=r["passes"], placebo_floor_pp=r["placebo_floor_pp"]))
# name-proxy contrasts
for g, ref in (("black", "white"), ("hispanic", "white"), ("asian", "white"), ("arab", "white")):
    for m in ("jev-1.13.0", "jev-1.14.0"):
        r = next(x for x in S if x["model"] == m and x["comparison"] == "names_vs_white" and x["group"] == g and x["domain"] == "ALL_SIGNED")
        rows.append(dict(contrast=f"{g} names vs white names", model=m, mean_pp=r["mean_pp"], ci_lo_pp=r["ci_lo_pp"],
                         ci_hi_pp=r["ci_hi_pp"], q_bh=r["q_bh"], passes=r["passes"], placebo_floor_pp=r["placebo_floor_pp"]))
wr("fig1_contrasts_pooled.csv", rows)
labels = list(dict.fromkeys(r["contrast"] for r in rows))
fig, ax = plt.subplots(figsize=(7, 7.2))
for i, lab in enumerate(labels):
    for j, (m, c) in enumerate((("jev-1.13.0", BLUE), ("jev-1.14.0", ORANGE))):
        r = next(x for x in rows if x["contrast"] == lab and x["model"] == m)
        y = -i + (0.15 if j == 0 else -0.15)
        mean, lo, hi = float(r["mean_pp"]), float(r["ci_lo_pp"]), float(r["ci_hi_pp"])
        ax.plot([lo, hi], [y, y], color=c, lw=2, solid_capstyle="round")
        ax.plot(mean, y, "o", color=c, ms=5, mec="#fcfcfb", mew=1.5, label=m if i == 0 else None)
floor = float(rows[0]["placebo_floor_pp"])
ax.axvspan(-floor, floor, color=GRAY, alpha=0.25, lw=0, label=f"placebo noise floor (±{floor:.1f} pp)")
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks([-i for i in range(len(labels))], labels)
ax.set_xlabel("Favorability difference, pp (positive = first group treated better)")
ax.set_title("Identity contrasts, pooled over 24 decision templates", loc="left", color=INK, fontsize=10)
ax.legend(frameon=False, loc="lower left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_contrasts_pooled.png"), dpi=180); plt.close(fig)

# 2. Heatmap: contrast x domain (jev-1.13.0), only cells that pass are filled with numbers
doms = ["hiring", "lending", "trust", "suspicion", "competence", "moral", "threat", "help", "help_others"]
hm = []
for g, ref in keep:
    for d in doms:
        r = next(x for x in S if x["model"] == "jev-1.13.0" and x["comparison"] == "label_vs_ref" and x["group"] == g and x["domain"] == d)
        hm.append(dict(contrast=f"{g} vs {ref}", domain=d, mean_pp=r["mean_pp"], ci_lo_pp=r["ci_lo_pp"], ci_hi_pp=r["ci_hi_pp"], passes=r["passes"]))
wr("fig2_heatmap_domains.csv", hm)
klabels = [f"{g} vs {ref}" for g, ref in keep]
Z = [[float(next(x for x in hm if x["contrast"] == k and x["domain"] == d)["mean_pp"]) for d in doms] for k in klabels]
P = [[next(x for x in hm if x["contrast"] == k and x["domain"] == d)["passes"] == "True" for d in doms] for k in klabels]
fig, ax = plt.subplots(figsize=(8, 7))
im = ax.imshow(Z, cmap="RdBu", vmin=-20, vmax=20, aspect="auto")
for i in range(len(klabels)):
    for j in range(len(doms)):
        ax.text(j, i, f"{Z[i][j]:.0f}" if P[i][j] else "·", ha="center", va="center", fontsize=7.5,
                color=INK if abs(Z[i][j]) < 12 else "white")
ax.set_xticks(range(len(doms)), doms, rotation=30, ha="right")
ax.set_yticks(range(len(klabels)), klabels)
cb = fig.colorbar(im, ax=ax, shrink=0.6); cb.set_label("favorability difference, pp")
ax.set_title("jev-1.13.0 by domain (number = passes BH q<0.05 and noise floor; dot = does not)", loc="left", fontsize=9, color=INK)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_heatmap_domains.png"), dpi=180); plt.close(fig)

# 3. Isaac's case: predicted preferences, Republican vs Democrat vs no identity, plus the color placebo
C = rd("cells_labels.csv")
acts = ["pref_carbon_tax", "pref_pride", "pref_ev", "pref_museum", "pref_hiking", "pref_church", "pref_nascar", "pref_gun_show", "pref_water", "pref_sleep"]
groups = [("baseline", GRAY), ("democrat", BLUE), ("republican", ORANGE)]
pr = []
for a in acts:
    for g, _ in groups + [("color_green", None), ("color_red", None)]:
        vs = [float(x["value"]) for x in C if x["model"] == "jev-1.13.0" and x["group"] == g and x["tid"] == a]
        pr.append(dict(activity=a, group=g, mean_p_yes=round(sum(vs) / len(vs), 3), n=len(vs)))
wr("fig3_preferences_party.csv", pr)
fig, ax = plt.subplots(figsize=(7, 4.2))
w = 0.26
for j, (g, c) in enumerate(groups):
    ys = [next(x for x in pr if x["activity"] == a and x["group"] == g)["mean_p_yes"] for a in acts]
    ax.bar([i + (j - 1) * w for i in range(len(acts))], ys, width=w - 0.03, color=c, label=g if g != "baseline" else "no identity stated")
ax.set_xticks(range(len(acts)), [a[5:].replace("_", " ") for a in acts], rotation=30, ha="right")
ax.set_ylabel("P(yes), mean of 6 prompts")
ax.set_ylim(0, 1)
ax.set_title('"You are a Republican/Democrat. Do you want to ...?" (jev-1.13.0)', loc="left", fontsize=10, color=INK)
ax.legend(frameon=False, ncol=3, loc="upper left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_preferences_party.png"), dpi=180); plt.close(fig)

# 4. BBQ-style disambiguated accuracy gap
Bq = rd("bbq_ci.csv")
wr("fig4_bbq_gap.csv", Bq)
items = [r["item"] for r in Bq if r["model"] == "jev-1.13.0"]
fig, ax = plt.subplots(figsize=(7, 5))
for j, (m, c) in enumerate((("jev-1.13.0", BLUE), ("jev-1.14.0", ORANGE))):
    for i, it in enumerate(items):
        r = next(x for x in Bq if x["model"] == m and x["item"] == it)
        y = -i + (0.15 if j == 0 else -0.15)
        ax.plot([float(r["gap_lo"]), float(r["gap_hi"])], [y, y], color=c, lw=2, solid_capstyle="round")
        ax.plot(float(r["dis_gap_pp"]), y, "o", color=c, ms=5, mec="#fcfcfb", mew=1.5, label=m if i == 0 else None)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks([-i for i in range(len(items))], items)
ax.set_xlabel("Accuracy when evidence names stereotyped person minus\naccuracy when it names the other person, pp")
ax.set_title("With clear evidence, does Jev resist naming the stereotyped person?", loc="left", fontsize=10, color=INK)
ax.legend(frameon=False, loc="lower left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig4_bbq_gap.png"), dpi=180); plt.close(fig)
print("charts written to", OUT)
