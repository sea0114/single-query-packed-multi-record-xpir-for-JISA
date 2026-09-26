"""Only the authorized post-B0_PASS Section 6.4 protocol synchronization."""
from pathlib import Path
import json,difflib
ROOT=Path(__file__).resolve().parents[2]
OLD="""The next stage is explicit-width encrypted native validity, followed by
controlled benchmark preparation. The analytical-only external-baseline
policy remains unchanged."""
NEW="""The benchmark protocol is frozen before formal measurements. Its comparison
unit is a completed two-record task; repeated requests may execute concurrently
under the same total resource budget. Cold and online costs are reported
separately. The analytical-only external-baseline policy remains unchanged."""
def expected_section():
    before=(ROOT/"revision_notes/archive/pre_B0/Section5.tex").read_bytes()
    # Existing source mixes CRLF and LF across historical edits. Match the local
    # paragraph's bytes, without normalizing any unrelated source.
    candidates=[(OLD.encode().replace(b"\n",nl),NEW.encode().replace(b"\n",nl)) for nl in (b"\n",b"\r\n")]
    matches=[(old,new) for old,new in candidates if before.count(old)==1]
    assert len(matches)==1
    old,new=matches[0];return before.replace(old,new)
if __name__=="__main__":
    assert json.loads((ROOT/"revision_notes/B0_status.json").read_text())["B0_status"]=="PASS"
    target=ROOT/"Section5.tex";before=target.read_bytes()
    assert before==(ROOT/"revision_notes/archive/pre_B0/Section5.tex").read_bytes()
    after=expected_section();target.write_bytes(after)
    (ROOT/"revision_notes/B0_logs/manuscript.diff").write_text("".join(difflib.unified_diff(before.decode().splitlines(True),
        after.decode().splitlines(True),fromfile="pre_B0/Section5.tex",tofile="Section5.tex")),encoding="utf-8")
    print("Section 6.4 minimal protocol sync applied after B0_PASS")
