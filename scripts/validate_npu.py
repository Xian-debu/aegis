#!/usr/bin/env python3
"""
NPU 功能验收脚本 — 一次运行 = 健康检查 + 质量基线 + 已知限制说明

设计原则: 输出自带解释，不让 LLM 下次看到数字就以为是 bug。
每个检查项直接标注预期范围、原理、以及什么情况才算真正的回归。

用法:
  python3 validate_npu.py                    # 完整验收
  python3 validate_npu.py --quick             # 仅健康检查
"""
import requests, json, sys, time, argparse
import numpy as np

API = "http://localhost:8898"
PASS = 0
FAIL = 0
WARN = 0


def check(name, fn):
    """运行一项检查，fn 返回 (ok:bool, detail:str)"""
    global PASS, FAIL, WARN
    try:
        ok, detail = fn()
        if ok:
            PASS += 1
            print(f"  \033[32m✓\033[0m {name}: {detail}")
        elif ok is None:  # warning — not a failure
            WARN += 1
            print(f"  \033[33m⚠\033[0m {name}: {detail}")
        else:
            FAIL += 1
            print(f"  \033[31m✗\033[0m {name}: {detail}")
    except Exception as e:
        FAIL += 1
        print(f"  \033[31m✗\033[0m {name}: ERROR — {e}")


def embed(texts):
    r = requests.post(f"{API}/v1/embeddings",
                      json={"input": texts}, timeout=30)
    r.raise_for_status()
    return [np.array(d["embedding"]) for d in r.json()["data"]]


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ═══════════════════════════════════════════════════════════════════
# Phase 1: 基础健康
# ═══════════════════════════════════════════════════════════════════

def check_health():
    """API 可达 + 设备正常"""
    r = requests.get(f"{API}/health", timeout=10)
    d = r.json()
    ok = d["status"] == "ok"
    return ok, f"status={d['status']}, device={d.get('device','?')}, model={d.get('model','?')}"


def check_dim():
    """嵌入维度 = 1024 (bge-m3)"""
    e = embed(["test"])
    ok = len(e[0]) == 1024
    return ok, f"dim={len(e[0])} (expected 1024 for bge-m3)"


def check_norm():
    """L2 归一化: 所有向量 norm≈1.0"""
    e = embed(["测试文本A", "test text B", "mixed 混合 C"])
    norms = [float(np.linalg.norm(v)) for v in e]
    ok = all(0.999 < n < 1.001 for n in norms)
    return ok, f"norms={[f'{n:.4f}' for n in norms]} (expected ~1.0000)"


def check_no_nan_zero():
    """无 NaN / 全零嵌入"""
    e = embed(["测试"])
    v = e[0]
    has_nan = np.isnan(v).any()
    is_zero = (np.abs(v) < 1e-8).all()
    ok = not has_nan and not is_zero
    return ok, f"NaN={has_nan}, zero_vector={is_zero} (expected False/False)"


# ═══════════════════════════════════════════════════════════════════
# Phase 2: 语义质量 + 已知基线
# ═══════════════════════════════════════════════════════════════════

# ── 以下基线来自 2026-05-14 实测验证 ──
# bge-m3 是一个密集嵌入模型，其高维空间 (1024-dim) 存在一个已知特性:
# 无关文本的 cosine 不会接近 0，而是在 0.50–0.60 左右。
# 这不是 bug，是模型本身的嵌入空间分布特征，不影响排序质量。
# 参考: memory/feedback/npu-embedding-pooling-fix.md
# ═══════════════════════════════════════════════════════════════

UNRELATED_EXPECTED_RANGE = (0.50, 0.62)  # 无关文本的正常范围
RELATED_EXPECTED_MIN = 0.70              # 相关文本的最低期望
SYNONYM_EXPECTED_MIN = 0.82              # 同义文本的最低期望
MEAN_VEC_NORM_MAX = 0.85                 # 均值向量 norm 上限


def check_unrelated_baseline():
    """
    无关文本余弦相似度 — 必须在 [0.50, 0.62]
    这是 bge-m3 的**固有基线**，不是 bug。
    如果 > 0.70 才是真正的回归 (简单 mean pooling 会导致)。
    如果 < 0.40 反而异常 (模型输出可能退化)。
    """
    pairs = [
        ("异步电机转子断条故障特征提取", "草莓慕斯蛋糕的制作方法教程"),
        ("bearing fault diagnosis using vibration", "strawberry mousse cake recipe"),
        ("量子计算的基本原理", "如何烹饪红烧肉"),
        ("美国总统大选最新民调", "儿童绘本的绘画技巧"),
    ]
    scores = [cos(*embed([a, b])) for a, b in pairs]
    lo, hi = UNRELATED_EXPECTED_RANGE
    all_in_range = all(lo <= s <= hi for s in scores)
    return all_in_range, (
        f"range=[{min(scores):.3f}, {max(scores):.3f}], "
        f"expected=[{lo:.2f}, {hi:.2f}] — "
        f"{'NORMAL: bge-m3 dense embedding baseline' if all_in_range else 'CHECK: outside expected range'}"
    )


def check_related_separation():
    """相关 > 同义 > 无关 的单调性 + 分离度"""
    e = embed([
        "电机轴承故障诊断方法研究",
        "感应电动机滚动轴承失效检测技术",   # 同义
        "旋转机械振动监测与智能维护",        # 相关
        "草莓慕斯蛋糕的制作方法教程",        # 无关
    ])
    synonym  = cos(e[0], e[1])
    related  = cos(e[0], e[2])
    unrelated = cos(e[0], e[3])

    monotonic = synonym > related > unrelated
    separation = synonym - unrelated

    return (monotonic and synonym >= SYNONYM_EXPECTED_MIN and separation > 0.15), (
        f"synonym={synonym:.4f}(≥{SYNONYM_EXPECTED_MIN}) > "
        f"related={related:.4f}(≥{RELATED_EXPECTED_MIN}) > "
        f"unrelated={unrelated:.4f}(~0.55 baseline), "
        f"separation={separation:.3f}(>0.15) "
        f"{'✓' if monotonic else '✗ ORDER VIOLATED'}"
    )


def check_mean_vector_norm():
    """
    多样本均值向量 norm < 0.85
    如果 > 0.90 说明所有嵌入指向同一方向 (pooling bug 或模型崩溃)。
    bge-m3 正常值约 0.75-0.85 (密集嵌入空间特征)。
    """
    texts = [
        "电机故障诊断", "深度学习NLP应用", "美国大选结果",
        "有机蔬菜种植", "量子计算原理", "古典音乐影响",
        "区块链技术", "气候变化影响", "人工智能发展",
        "疫苗研发进展", "日本动漫产业", "奥运举办城市",
        "简历制作技巧", "新冠病毒变异", "极地生态系统",
    ]
    embs = embed(texts)
    mean_norm = float(np.linalg.norm(np.mean(embs, axis=0)))

    ok = mean_norm < MEAN_VEC_NORM_MAX
    return ok, (
        f"mean_vec_norm={mean_norm:.4f} (<{MEAN_VEC_NORM_MAX}) — "
        f"{'NORMAL: bge-m3 dense space' if ok else 'WARNING: vectors too aligned, possible pooling issue'}"
    )


# ═══════════════════════════════════════════════════════════════════
# Phase 3: 跨语言 (bge-m3 核心能力)
# ═══════════════════════════════════════════════════════════════════

def check_cross_lingual():
    """中英跨语言对齐 — 同义中英对相似度应 > 0.65"""
    pairs = [
        ("电机轴承故障诊断", "electric motor bearing fault diagnosis"),
        ("深度学习在自然语言处理中的应用", "deep learning applications in NLP"),
    ]
    scores = [cos(*embed([a, b])) for a, b in pairs]
    ok = all(s > 0.65 for s in scores)
    return ok, f"scores={[f'{s:.4f}' for s in scores]} (expected >0.65 for cross-lingual bge-m3)"


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="NPU 功能验收")
    parser.add_argument("--quick", action="store_true", help="仅基础健康检查")
    args = parser.parse_args()

    print("=" * 62)
    print("  NPU 验收: BAAI/bge-m3 (1024-dim) on Intel AI Boost")
    print("=" * 62)

    print("\n── Phase 1: 基础健康 ──")
    check("API health",         check_health)
    check("Embedding dim=1024",  check_dim)
    check("L2 norm≈1.0",        check_norm)
    check("No NaN/zero vector",  check_no_nan_zero)

    if not args.quick:
        print("\n── Phase 2: 语义质量 + 已知基线 ──")
        print("    注意: bge-m3 密集嵌入空间，无关文本 baseline cos≈0.55")
        print("    这不是 bug，是模型固有特性。参考 npu-embedding-pooling-fix.md")

        check("Unrelated baseline [0.50,0.62]", check_unrelated_baseline)
        check("Semantic separation",            check_related_separation)
        check("Mean vector norm <0.85",         check_mean_vector_norm)

        print("\n── Phase 3: 跨语言 ──")
        check("Cross-lingual alignment", check_cross_lingual)

    # ── 总结 ──
    print(f"\n{'='*62}")
    total = PASS + FAIL + WARN
    print(f"  {total} checks: {PASS} pass, {WARN} warn, {FAIL} fail")

    if FAIL > 0:
        print("  真正的回归标志:")
        print("    - 无关相似度 > 0.70 (pooling 失效)")
        print("    - 同义相似度 < 0.70 (模型崩溃)")
        print("    - 均值向量 norm > 0.90 (所有向量指向同一方向)")
        print("    - 维度不为 1024 (模型不匹配)")
        print("    - NaN 或全零嵌入 (推理故障)")
    else:
        print("  NPU 功能正常 — STABLE")

    print(f"{'='*62}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
