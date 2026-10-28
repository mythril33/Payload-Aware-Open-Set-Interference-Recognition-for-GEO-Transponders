"""Lesson 01: tensors and autograd, starting from numpy habits.

Run: python lessons/01_tensors_autograd.py   (standalone: does not import rfml)
Every claim below is an assert; a failing check stops the lesson.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless; must come before pyplot is imported
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

T = torch.Tensor
RESULTS = Path(__file__).resolve().parents[1] / "results"
TRUE_W, TRUE_B = 2.5, -1.0  # ground truth of the synthetic line fit
LR, STEPS = 0.1, 200  # stable: lr < 2 / lambda_max, and lambda_max is about 2 here


def section(title: str) -> None:
    print(f"\n== {title} ==")


def make_data(n: int = 100) -> tuple[T, T]:
    """Noisy samples of y = 2.5 x - 1 with x ~ U(-1, 1) and noise std 0.1."""
    x = torch.rand(n) * 2 - 1
    return x, TRUE_W * x + TRUE_B + 0.1 * torch.randn(n)


def mse_grads_by_hand(w: T, b: T, x: T, y: T) -> tuple[T, T]:
    """Closed-form gradients of L = mean((w*x + b - y)^2).

    Chain rule per sample: dL/dpred = 2 (pred - y) / N, dpred/dw = x, dpred/db = 1.
    So dL/dw = mean(2 (pred - y) x) and dL/db = mean(2 (pred - y)).
    """
    residual = w * x + b - y
    return (2 * residual * x).mean(), (2 * residual).mean()


def tensors_vs_numpy() -> None:
    section("1. Tensors vs numpy")
    # numpy floats are float64; torch floats default to float32 (what GPUs and layers use).
    a, t = np.zeros(4), torch.zeros(4)
    print(f"numpy dtype {a.dtype}, torch dtype {t.dtype}, shape {tuple(t.shape)}")
    assert a.dtype == np.float64 and t.dtype == torch.float32
    # Slicing returns a VIEW (shared memory); clone() makes an independent copy.
    view = t[:2]
    view[0] = 9.0  # writes through to t
    assert t[0].item() == 9.0
    c = t.clone()
    c[1] = 3.0  # does not touch t
    assert t[1].item() == 0.0
    # Broadcasting aligns shapes from the right; size-1 dims stretch.
    # (2,1,4) + (3,1): align -> (2,1,4) vs (_,3,1) -> (2,3,4). Wrong shapes can still run, so assert them.
    out = torch.ones(2, 1, 4) + torch.ones(3, 1)
    assert tuple(out.shape) == (2, 3, 4)
    print(f"views share memory, clone() copies, broadcast (2,1,4) + (3,1) -> {tuple(out.shape)}")
    # from_numpy SHARES memory (CPU only) and keeps float64; .float() copies to float32.
    shared = torch.from_numpy(a)
    shared[2] = 5.0
    assert a[2] == 5.0 and shared.dtype == torch.float64
    # .numpy() fails for GPU tensors or tensors that require grad: detach and move first.
    assert shared.float().detach().cpu().numpy().dtype == np.float32


def autograd_basics() -> None:
    section("2. Autograd: backward, accumulation, no_grad, detach")
    x = torch.tensor(3.0, requires_grad=True)  # record operations on x
    (x**2 + 2 * x).backward()  # d/dx = 2x + 2 = 8 at x = 3
    g1 = x.grad.item()
    (x**2 + 2 * x).backward()  # a second backward ADDS to .grad
    g2 = x.grad.item()
    assert (g1, g2) == (8.0, 16.0)
    print(f"grad after one backward {g1}, after a second {g2} (accumulated)")
    x.grad.zero_()  # clear before the next step (optimizer.zero_grad does this)
    with torch.no_grad():  # inference: no graph built, less memory
        assert not (x * 2).requires_grad
    assert not (x * 2).detach().requires_grad  # same values, cut off from the graph
    print("no_grad() and detach() both stop gradient tracking")


def manual_gradient_check(x: T, y: T) -> None:
    section("3. Hand formula vs autograd")
    w = torch.tensor(0.5, requires_grad=True)
    b = torch.tensor(0.1, requires_grad=True)
    ((w * x + b - y) ** 2).mean().backward()  # autograd fills w.grad and b.grad
    gw, gb = mse_grads_by_hand(w.detach(), b.detach(), x, y)
    print(f"dL/dw  hand {gw.item():+.6f}  autograd {w.grad.item():+.6f}")
    print(f"dL/db  hand {gb.item():+.6f}  autograd {b.grad.item():+.6f}")
    assert torch.allclose(gw, w.grad) and torch.allclose(gb, b.grad)


def gradient_descent_by_hand(x: T, y: T) -> tuple[float, float, list[float]]:
    section("4. Gradient descent by hand")
    w = torch.zeros((), requires_grad=True)  # leaf tensors start at 0
    b = torch.zeros((), requires_grad=True)
    losses = []
    # In-place updates to a leaf that requires grad are only legal under no_grad,
    # and the update itself must not be recorded in the graph.
    with torch.no_grad():
        for _ in range(STEPS):
            gw, gb = mse_grads_by_hand(w, b, x, y)
            w -= LR * gw  # step against the gradient
            b -= LR * gb
            losses.append(((w * x + b - y) ** 2).mean().item())
    # Closed-form least squares is the answer GD should converge to.
    design = np.column_stack([x.numpy(), np.ones(len(x))])
    (w_ls, b_ls), *_ = np.linalg.lstsq(design, y.numpy().astype(np.float64), rcond=None)
    print(f"GD:            w={w.item():.4f}, b={b.item():.4f}  (truth {TRUE_W}, {TRUE_B})")
    print(f"least squares: w={w_ls:.4f}, b={b_ls:.4f}")
    assert abs(w.item() - w_ls) < 1e-3 and abs(b.item() - b_ls) < 1e-3
    return w.item(), b.item(), losses


def fit_with_nn(x: T, y: T) -> tuple[float, float]:
    section("5. Same fit with nn.Linear + SGD + MSELoss")
    layer = nn.Linear(1, 1)  # computes weight * x + bias
    nn.init.zeros_(layer.weight)  # same start as section 4
    nn.init.zeros_(layer.bias)
    opt = torch.optim.SGD(layer.parameters(), lr=LR)  # plain p -= lr * p.grad
    loss_fn = nn.MSELoss()
    xs, ys = x.unsqueeze(1), y.unsqueeze(1)  # layers expect (N, features)
    for _ in range(STEPS):
        opt.zero_grad()  # the library version of zeroing .grad by hand
        loss_fn(layer(xs), ys).backward()
        opt.step()
    return layer.weight.item(), layer.bias.item()


def save_results(x: T, y: T, hand: tuple[float, float], lib: tuple[float, float],
                 losses: list[float]) -> None:
    RESULTS.mkdir(exist_ok=True)
    payload = {"lesson": "01_tensors_autograd", "n_samples": len(x), "lr": LR, "steps": STEPS,
               "truth_w_b": [TRUE_W, TRUE_B], "hand_w_b": list(hand), "nn_w_b": list(lib),
               "final_mse_hand": losses[-1]}
    # allow_nan=False: a NaN raises here instead of silently writing invalid JSON.
    (RESULTS / "01_tensors_autograd.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(9, 3.5))
    ax0.semilogy(losses)
    ax0.set(title="Hand gradient descent", xlabel="step", ylabel="MSE")
    ax1.scatter(x.numpy(), y.numpy(), s=8, label="samples")
    xs = np.array([-1.0, 1.0])
    ax1.plot(xs, hand[0] * xs + hand[1], "r", label="fit")
    ax1.set(title="Line fit", xlabel="x", ylabel="y")
    ax1.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "01_tensors_autograd.png", dpi=110)
    plt.close(fig)


def summary() -> None:
    section("6. What we just learned")
    for line in [
        "Tensors look like numpy arrays but default to float32, can live on a GPU and can record gradients.",
        "Slicing gives a view that shares memory; clone() gives an independent copy.",
        "Broadcasting stretches size-1 dims from the right; assert shapes, a wrong one can still run.",
        "requires_grad=True makes autograd record operations; loss.backward() fills .grad with dLoss/dparam.",
        "Gradients accumulate across backward() calls, so zero them every step.",
        "no_grad() is for updates and inference; detach() cuts a tensor off the graph; .numpy() needs CPU.",
        "Check a hand-derived gradient against autograd before trusting a custom loss.",
        "An optimizer is just p -= lr * p.grad; nn.Linear + SGD + MSELoss reproduced the hand loop.",
    ]:
        print(f"- {line}")


def main() -> None:
    torch.set_num_threads(4)
    torch.manual_seed(0)  # same data and same output on every run
    tensors_vs_numpy()
    autograd_basics()
    x, y = make_data()
    manual_gradient_check(x, y)
    w, b, losses = gradient_descent_by_hand(x, y)
    w_nn, b_nn = fit_with_nn(x, y)
    print(f"hand loop vs nn.Linear: |dw| = {abs(w - w_nn):.1e}, |db| = {abs(b - b_nn):.1e}")
    assert abs(w - w_nn) < 1e-4 and abs(b - b_nn) < 1e-4  # same algorithm, two code paths
    save_results(x, y, (w, b), (w_nn, b_nn), losses)
    summary()


if __name__ == "__main__":
    main()
