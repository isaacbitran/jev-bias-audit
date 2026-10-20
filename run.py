"""Build every prompt in the audit, ask Jev, and cache every answer on disk.

Usage: python3 -I run.py [--models jev-1.13.0,jev-1.14.0] [--reps 2] [--dry]
Output: cache.jsonl (one line per answered question) and items.jsonl (metadata).
"""
import hashlib, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bank, jev

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache.jsonl")
BATCH = 220
BUDGET_USD = 9.0


def q_payload(fmt, text, criteria):
    q = {"type": fmt, "instructions": text}
    if criteria is not None:
        q["criteria"] = criteria
    return q


def build_items():
    items = []
    # 1. single-person Noul/Score prompts
    idents = [("baseline", "baseline", "baseline", "")]
    idents += [(a, g, "label", np) for a, g, np in bank.LABELS]
    idents += [("name_" + race, race + "_" + gen, "name", n) for race, gen, n in bank.NAMES]
    for t in bank.T:
        for pi in range(3):
            for person in ("you", "they"):
                for attr, group, kind, val in idents:
                    lead = bank.identity_sentence(person, kind, val)
                    text = bank.render(t, pi, person, lead)
                    items.append(dict(exp="single", tid=t["tid"], domain=t["domain"], fmt=t["fmt"], sign=t["sign"],
                                      para=pi, person=person, attr=attr, group=group, kind=kind, value=val,
                                      state="", q=q_payload(t["fmt"], text, t["criteria"])))
    # 2. placement check: identity in `state` instead of the question (third person, labels)
    for t in bank.T:
        if t["domain"] not in ("hiring", "lending", "suspicion", "threat", "trust"):
            continue
        for pi in range(3):
            for attr, group, kind, val in idents:
                if kind == "name":
                    continue
                state = bank.identity_sentence("they", kind, val) if kind != "baseline" else "This is a person."
                text = bank.render(t, pi, "they", "")
                items.append(dict(exp="placement", tid=t["tid"], domain=t["domain"], fmt=t["fmt"], sign=t["sign"],
                                  para=pi, person="they", attr=attr, group=group, kind=kind, value=val,
                                  state=state, q=q_payload(t["fmt"], text, t["criteria"])))
    # 3. pairwise Choice: every within-attribute pair, both mention orders, with and without an "equal" option
    by_attr = {}
    for a, g, np in bank.LABELS:
        by_attr.setdefault(a, []).append((g, np))
    for attr, groups in by_attr.items():
        pairs = [(groups[i], groups[j]) for i in range(len(groups)) for j in range(i + 1, len(groups))]
        if attr == "placebo":  # colors with colors, months with months
            pairs = [p for p in pairs if p[0][0].split("_")[0] == p[1][0].split("_")[0]]
        for (g1, np1), (g2, np2) in pairs:
            for domain, sign, paras in bank.PAIR_TASKS:
                for pi, para in enumerate(paras):
                    for order in (0, 1):
                        (ga, npa), (gb, npb) = ((g1, np1), (g2, np2)) if order == 0 else ((g2, np2), (g1, np1))
                        text = para.format(A=npa, B=npb)
                        for opt in ("forced", "equal"):
                            crit = {"first": f"The one who is {npa}", "second": f"The one who is {npb}"}
                            if opt == "equal":
                                crit["equal"] = "Neither; they should be treated the same"
                            items.append(dict(exp="pair", domain=domain, sign=sign, para=pi, attr=attr, g1=g1, g2=g2,
                                              order=order, opt=opt, ga=ga, gb=gb, state="",
                                              q=q_payload("choice", text, crit)))
    # 4. BBQ-style items: ambiguous and disambiguated, both mention orders, both option orders
    def the(np):
        return "the " + np.split(" ", 1)[1]
    for iid, attr, tgt, oth, ctx, qs, dis in bank.BBQ:
        for mention in (0, 1):
            F, G = (tgt, oth) if mention == 0 else (oth, tgt)
            base = ctx.format(F=F[0].upper() + F[1:], G=G)
            for cond in ("ambig", "dis_target", "dis_other"):
                extra = ""
                if cond != "ambig":
                    X = the(tgt if cond == "dis_target" else oth)
                    s = dis.format(X=X)
                    extra = " " + s[0].upper() + s[1:]
                for qi, qq in enumerate(qs):
                    for optorder in (0, 1):
                        opts = [("target", "The " + the(tgt)[4:]), ("other", "The " + the(oth)[4:])]
                        if optorder:
                            opts = opts[::-1]
                        crit = {k: v for k, v in opts}
                        crit["unknown"] = "Cannot be determined from the information given"
                        items.append(dict(exp="bbq", iid=iid, attr=attr, mention=mention, cond=cond, qi=qi,
                                          optorder=optorder, state="", q=q_payload("choice", base + extra + " " + qq, crit)))
    return items


def key(model, rep, state, q):
    return hashlib.sha1(json.dumps([model, rep, state, q]).encode()).hexdigest()


def load_cache():
    c = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            for line in f:
                r = json.loads(line)
                c[r["k"]] = r
    return c


def main():
    args = sys.argv[1:]
    models = ["jev-1.13.0", "jev-1.14.0"]
    reps = 2
    if "--models" in args:
        models = args[args.index("--models") + 1].split(",")
    if "--reps" in args:
        reps = int(args[args.index("--reps") + 1])
    exps = None
    if "--exps" in args:
        exps = set(args[args.index("--exps") + 1].split(","))
    items = build_items()
    with open(os.path.join(HERE, "items.jsonl"), "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    if exps:
        items = [i for i in items if i["exp"] in exps]
    cache = load_cache()
    todo = {}
    for m in models:
        for rep in range(reps):
            for it in items:
                k = key(m, rep, it["state"], it["q"])
                if k in cache:
                    continue
                todo.setdefault((m, rep, it["state"]), {})[k] = it["q"]
    n = sum(len(v) for v in todo.values())
    print(f"items={len(items)} unique-todo={n} batches~{sum((len(v)+BATCH-1)//BATCH for v in todo.values())}")
    if "--dry" in args:
        return
    jobs = []
    for (m, rep, state), qs in todo.items():
        ks = list(qs)
        for i in range(0, len(ks), BATCH):
            jobs.append((m, rep, state, {k: qs[k] for k in ks[i:i + BATCH]}))
    lock = threading.Lock()
    done = [0]
    out = open(CACHE, "a")

    def work(job):
        m, rep, state, qs = job
        if jev.cost_usd() > BUDGET_USD:
            return
        qmap = {f"q{i}": q for i, q in enumerate(qs.values())}
        ks = list(qs)
        r = jev.ask(state, qmap, model=m, retries=8)
        with lock:
            for i, k in enumerate(ks):
                out.write(json.dumps({"k": k, "model": r["model"], "rep": rep, "a": r["answers"][f"q{i}"]}) + "\n")
            out.flush()
            done[0] += 1
            if done[0] % 20 == 0:
                print(done[0], "/", len(jobs), jev.summary(), flush=True)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(work, jobs))
    out.close()
    print("final", jev.summary())


if __name__ == "__main__":
    main()
