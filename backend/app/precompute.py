"""Step A: run once per patient.  python -m app.precompute [--skip-llm]"""
import sys

from . import store
from .extract import extract_document
from .ingest import ingest
from .rules import run_rules
from .verify import verify_facts


def main() -> None:
    docs, segments = ingest()
    store.save("documents", docs)
    store.save("segments", segments)
    print(f"ingest: {len(docs)} documents, {len(segments)} segments")

    facts = []
    if "--skip-llm" not in sys.argv:
        seg_by_id = {s.id: s for s in segments}
        for d in docs:
            try:
                raw = extract_document(d, [s for s in segments if s.doc_id == d.id])
            except NotImplementedError as e:
                print(f"extract: skipped ({e})")
                break
            kept, dropped = verify_facts(raw, seg_by_id)
            facts += kept
            print(f"extract {d.id}: {len(kept)} kept, {len(dropped)} dropped")
    store.save("facts", facts)

    findings = run_rules(segments)
    store.save("findings", findings)
    print(f"rules: {len(findings)} findings")
    for f in findings:
        print(f"  - {f.title}: {f.explanation} {f.segment_ids}")


if __name__ == "__main__":
    main()
