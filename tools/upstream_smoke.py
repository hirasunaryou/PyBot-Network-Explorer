"""Real pinned upstream integration check, no mock or neural network."""
from network.bootstrap import ensure_upstream
from network.engine import Explorer


def main():
    source=ensure_upstream()
    explorer=Explorer(source)
    summary=explorer.system()
    assert summary["total"]["files"] > 100,summary["total"]
    assert summary["total"]["lines"] > 500000,summary["total"]
    session="network_smoke_0001"
    turn=explorer.ask(session,"Do you know how to calculate mean?")
    assert turn["selected_module"]=="answers",turn
    assert "The mean, which is what most people mean" in turn["reply"]
    assert len(turn["candidates"])>0
    trace=explorer.trace(session,0)
    assert trace["replay_equal"],trace["warning"]
    assert len(trace["frames"])>10
    assert len(trace["frames"])<=360
    assert trace["call_count"]>500
    assert trace["graph"]["observed_node_count"]>=len(trace["graph"]["nodes"])
    assert all(e["type"]=="observed" for e in trace["graph"]["edges"])
    assert trace["frames"][0]["kind"]=="start"
    assert trace["frames"][-1]["kind"]=="final"
    origin=next((s for s in trace["source_matches"]
                 if s["path"]=="bot/knowledge/maths.py" and s["exact"]),None)
    assert origin and origin["symbol"]=="_AVERAGE_EXPLAIN",origin
    assert origin["line"]==5101,origin
    assert 5196 in origin["references"],origin
    assert len(explorer.session(session).turns)==1
    print("REAL PYBOT:",turn["selected_module"],"-",turn["reply"][:100])
    print("NETWORK:",trace["call_count"],"calls,",trace["graph"]["observed_node_count"],
          "functions,",len(trace["frames"]),"timeline frames")
    print("LITERAL:",origin["path"],origin["line"],origin["symbol"])
    print("REPLAY MATCH:",trace["replay_equal"])
    print("PASS: pinned real PyBot, network, provenance and untouched live memory")


if __name__=="__main__":
    main()
