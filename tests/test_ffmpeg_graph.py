import re

from mini.render.ffmpeg_cmd import build_filter_complex


def test_concat_pairs_and_loudnorm():
    segments = [
        {"src_index": 0, "in": 1.0, "out": 2.0},
        {"src_index": 1, "in": 3.0, "out": 4.0},
        {"src_index": 0, "in": 5.0, "out": 6.0},
    ]
    graph, vmap, amap = build_filter_complex(
        segments,
        inputs_count=2,
        logo_idx=None,
        width=1080,
        height=1920,
        source_audio={0: True, 1: True},
    )
    assert f"concat=n={len(segments)}:v=1:a=1" in graph
    assert re.search(r"\[v0\]\[a0\]\[v1\]\[a1\]\[v2\]\[a2\]concat", graph)
    assert graph.index("[acat]") < graph.index("loudnorm")
    assert "format=yuv420p" in graph
    assert vmap == "[vout]"
    assert amap == "[aout]"
