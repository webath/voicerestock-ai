"""Read models κοινά με το stdlib mock. Μετράνε καταγραφές, όχι υποθετικό ROI."""
from datetime import datetime


def operations(suggestions, calls, changes):
    drafts = [s for s in suggestions if s["status"] == "draft_created"]
    durations = []
    for c in calls:
        try:
            seconds = (datetime.fromisoformat(c["ended_at"].replace("Z", "+00:00")) -
                       datetime.fromisoformat(c["started_at"].replace("Z", "+00:00"))).total_seconds()
            if seconds >= 0:
                durations.append(seconds)
        except (KeyError, TypeError, ValueError, AttributeError):
            pass
    return {"open": sum(s["status"] in {"proposed", "modified", "confirmed", "failed"} for s in suggestions),
            "drafts": len(drafts), "modified_drafts": sum(any(l["QTY1"] != l.get("QTY_RECOMMENDED", l["QTY1"]) for l in s["LINES"]) for s in drafts),
            "draft_value_eur": round(sum(s.get("VALUE", 0) for s in drafts), 2),
            "calls": len(calls), "timed_calls": len(durations),
            "average_call_seconds": round(sum(durations) / len(durations), 1) if durations else None,
            "changes": changes,
            "value_basis": "Καθαρή αξία drafts σε τιμές καταλόγου. Δεν είναι πραγματοποιημένος τζίρος ή εξοικονόμηση."}


def trace(suggestion, events, calls):
    sid = suggestion["id"]
    matching = [{"at": t["at"], "actor": f"voice:{c['call_sid']}", "action": "voice_confirmation",
                 "outcome": t["text"], "snapshot": None}
                for c in calls for t in c.get("transcript", [])
                if t.get("suggestion_id") == sid and t.get("type") == "confirmation"]
    return {"suggestion_id": sid, "status": suggestion["status"], "erp_draft_id": suggestion.get("erp_draft_id"),
            "evidence": [{"MTRL": l["MTRL"], "ITEM_NAME": l["ITEM_NAME"], "UNIT": l["UNIT"],
                          "QTY_RECOMMENDED": l.get("QTY_RECOMMENDED"), "QTY1": l["QTY1"],
                          "PREDICTED_DEPLETION_DATE": l.get("PREDICTED_DEPLETION_DATE"), "evidence": l.get("evidence", {})}
                         for l in suggestion["LINES"]],
            "events": sorted(events + matching, key=lambda e: (e["at"], e.get("sequence", 0)))}
