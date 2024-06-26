import warnings
from typing import Iterable

import torch

from fosco.verifier.types import SYMBOL
from fosco.verifier.utils import get_solver_fns
from fosco.models import TorchSymDiffModel, TorchSymModel
from fosco.systems import ControlAffineDynamics, UncertainControlAffineDynamics


class DoubleIntegratorCBF(TorchSymDiffModel):
    def __init__(self, system: ControlAffineDynamics):
        super().__init__()
        self._system = system
        self._safety_dist = 1.5  # todo this should be taken from system
        self._amax = 5.0  # todo this should be taken from system control input

        self._eps = 1e-6  # used to avoid division by zero and sqrt of negative numbers in gradient

    @property
    def input_size(self) -> int:
        return self._system.n_vars

    @property
    def output_size(self) -> int:
        return 1

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        h(x) = | x - x_o |^2 - v / a_max - R^2

        simpler
        h(x) = | x + dt * v - x_o |^2 - R^2
        """
        self._assert_forward_input(x=x)

        dpT = x[:, :2].reshape(-1, 1, 2)
        dv = x[:, 2:].reshape(-1, 2, 1)
        dp_norm = torch.norm(dpT, dim=-1).squeeze()

        vrel = (dpT @ dv).squeeze() / dp_norm
        dist_cap = torch.maximum(torch.zeros_like(vrel), dp_norm - self._safety_dist)

        hx = vrel + torch.sqrt(self._amax * dist_cap)
        hx = hx.reshape(x.shape[0])

        self._assert_forward_output(x=hx)
        return hx

    def forward_smt(
        self, x: list[SYMBOL]
    ) -> tuple[SYMBOL, Iterable[SYMBOL], Iterable[SYMBOL]]:
        raise NotImplementedError("forward_smt not implemented for DoubleIntegratorCBF")

    def gradient(self, x: torch.Tensor) -> torch.Tensor:
        self._assert_forward_input(x=x)

        dp_norm = torch.norm(x[:, :2], dim=-1)
        dist_cap = torch.maximum(
            self._eps * torch.ones_like(dp_norm), dp_norm - self._safety_dist
        )

        dhdx0 = (
            x[:, 0] * torch.sqrt(self._amax * dist_cap) / (2 * dist_cap * dp_norm)
            - x[:, 0] * (x[:, 0] * x[:, 2] + x[:, 1] * x[:, 3]) / dp_norm ** 3
            + x[:, 2] / dp_norm
        )

        dhdx1 = (
            x[:, 1] * torch.sqrt(self._amax * dist_cap) / (2 * dist_cap * dp_norm)
            - x[:, 1] * (x[:, 0] * x[:, 2] + x[:, 1] * x[:, 3]) / dp_norm ** 3
            + x[:, 3] / dp_norm
        )

        dhdx2 = x[:, 0] / dp_norm
        dhdx3 = x[:, 1] / dp_norm

        dhdx = torch.stack([dhdx0, dhdx1, dhdx2, dhdx3], dim=-1)

        self._assert_gradient_output(x=dhdx)
        return dhdx

    def gradient_smt(
        self, x: Iterable[SYMBOL]
    ) -> tuple[Iterable[SYMBOL], Iterable[SYMBOL], Iterable[SYMBOL]]:
        raise NotImplementedError(
            "gradient_smt not implemented for DoubleIntegratorCBF"
        )

    def _assert_forward_input(self, x: torch.Tensor) -> None:
        state_dim = self._system.n_vars
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch input to be tensor, got {type(x)}"
        assert (
            len(x.shape) == 2
        ), f"expected batch input (batch, {state_dim}), got {x.shape}"
        assert (
            x.shape[1] == state_dim
        ), f"expected batch input (batch, {state_dim}), got {x.shape}"

    def _assert_forward_output(self, x: torch.Tensor) -> None:
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch output to be tensor, got {type(x)}"
        assert len(x.shape) == 1, f"expected output of shape (batch,), got {x.shape}"

    def _assert_gradient_output(self, x: torch.Tensor) -> None:
        state_dim = self._system.n_vars
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch output to be tensor, got {type(x)}"
        assert (
            len(x.shape) == 2
        ), f"expected batch output (batch, {state_dim}), got {x.shape}"
        assert (
            x.shape[1] == state_dim
        ), f"expected batch output (batch, {state_dim}), got {x.shape}"

    def _assert_forward_smt_input(self, x: Iterable[SYMBOL]) -> None:
        state_dim = self._system.n_vars
        assert all(
            [isinstance(xi, SYMBOL) for xi in x]
        ), f"expected symbolic input, got {x}"
        assert (
            len(x) == state_dim
        ), f"expected {state_dim} state variables, got input of length {len(x)}"

    def _assert_forward_smt_output(self, x: Iterable[SYMBOL]) -> None:
        assert isinstance(x, SYMBOL), f"expected symbolic output, got {x}"

    def _assert_gradient_smt_output(self, x: Iterable[SYMBOL]) -> None:
        state_dim = self._system.n_vars
        assert len(x.shape) == 2, f"expected shape (1, {state_dim}), got {x.shape}"
        assert (
            x.shape[1] == state_dim
        ), f"expected shape (1, {state_dim}), got {x.shape}"
        assert all(
            [isinstance(xi, SYMBOL) for xi in x[0]]
        ), f"expected symbolic grad w.r.t. input, got {x}"

    def save(self, *args, **kwargs):
        warnings.warn("Saving is not supported for hand-crafted models")

    @staticmethod
    def load(*args, **kwargs):
        warnings.warn("Loading is not supported for hand-crafted models")


class DoubleIntegratorCompensatorAdditiveBoundedUncertainty(TorchSymModel):
    def __init__(self, h: TorchSymDiffModel, system: UncertainControlAffineDynamics):
        super().__init__()
        self._system = system
        self._h = h  # CBF (we use its gradient)
        self._safety_dist = 1.0  # todo this should be taken from system
        self._z_bound = 1.0  # todo this should be taken from system uncertainty

    @property
    def input_size(self) -> int:
        return self._system.n_vars

    @property
    def output_size(self) -> int:
        return 1

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        sigma(x) = || h.gradient(x) || * z_bound
        """
        self._assert_forward_input(x=x)
        dhdx = self._h.gradient(x=x)
        sigma = torch.norm(dhdx, dim=-1) * self._z_bound
        self._assert_forward_output(x=sigma)
        return sigma

    def forward_smt(
        self, x: list[SYMBOL]
    ) -> tuple[SYMBOL, Iterable[SYMBOL], Iterable[SYMBOL]]:
        """
        Problem: z3 is not able to cope with sqrt.

        Solution: forward pass as conjunction of two constraints
        - note that sigma = sqrt(dhdx[0] ** 2 + dhdx[1] ** 2) is equivalent to
          sigma ** 2 = dhdx[0] ** 2 + dhdx[1] ** 2
        - then we forward pass as
        And(sigma * z_bound, sigma ** 2 = dhdx[0] ** 2 + dhdx[1] ** 2)
        """
        self._assert_forward_smt_input(x=x)
        fns = get_solver_fns(x=x)

        dhdx, dhdx_constraints, symbolic_vars = self._h.gradient_smt(x=x)
        norm = fns["RealVar"]("norm")
        symbolic_vars.append(norm)

        norm_constraint = [
            norm * norm == dhdx[0, 0] ** 2 + dhdx[0, 1] ** 2,
            norm >= 0.0,
        ]
        sigma = norm * self._z_bound

        self._assert_forward_smt_output(x=sigma)
        return sigma, dhdx_constraints + norm_constraint, symbolic_vars

    def _assert_forward_input(self, x: torch.Tensor) -> None:
        state_dim = self._system.n_vars
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch input to be tensor, got {type(x)}"
        assert (
            len(x.shape) == 2
        ), f"expected batch input (batch, {state_dim}), got {x.shape}"
        assert (
            x.shape[1] == state_dim
        ), f"expected batch input (batch, {state_dim}), got {x.shape}"

    def _assert_forward_output(self, x: torch.Tensor) -> None:
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch output to be tensor, got {type(x)}"
        assert len(x.shape) == 1, f"expected output of shape (batch,), got {x.shape}"

    def _assert_forward_smt_input(self, x: Iterable[SYMBOL]) -> None:
        state_dim = self._system.n_vars
        assert all(
            [isinstance(xi, SYMBOL) for xi in x]
        ), f"expected symbolic input, got {x}"
        assert (
            len(x) == state_dim
        ), f"expected {state_dim} state variables, got input of length {len(x)}"

    def _assert_forward_smt_output(self, x: Iterable[SYMBOL]) -> None:
        assert isinstance(x, SYMBOL), f"expected symbolic output, got {x}"

    def save(self, *args, **kwargs):
        warnings.warn("Saving is not supported for hand-crafted models")

    @staticmethod
    def load(*args, **kwargs):
        warnings.warn("Loading is not supported for hand-crafted models")


class DoubleIntegratorTunableCompensatorAdditiveBoundedUncertainty(TorchSymModel):
    def __init__(self, h: TorchSymDiffModel, system: UncertainControlAffineDynamics):
        super().__init__()
        self._system = system
        self._h = h  # CBF (we use its gradient)
        self._safety_dist = 1.0  # todo this should be taken from system
        self._z_bound = 1.0  # todo this should be taken from system uncertainty

        # this accounts for ensuring robustness over entire belt
        # without this, the rcbf might result non valid
        self._epsilon = 0.1

    @property
    def input_size(self) -> int:
        return self._system.n_vars

    @property
    def output_size(self) -> int:
        return 1

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        sigma(x) = || h.gradient(x) || * z_bound * k(hx)
        """
        self._assert_forward_input(x=x)
        dhdx = self._h.gradient(x=x)
        sigma = torch.norm(dhdx, dim=-1) * self._z_bound * self._k_function(self._h(x))
        self._assert_forward_output(x=sigma)
        return sigma

    def forward_smt(
        self, x: list[SYMBOL]
    ) -> tuple[SYMBOL, Iterable[SYMBOL], Iterable[SYMBOL]]:
        """
        Problem: z3 is not able to cope with sqrt.

        Solution: forward pass as conjunction of two constraints
        - note that sigma = sqrt(dhdx[0] ** 2 + dhdx[1] ** 2) is equivalent to
          sigma ** 2 = dhdx[0] ** 2 + dhdx[1] ** 2
        - then we forward pass as
        And(sigma * z_bound, sigma ** 2 = dhdx[0] ** 2 + dhdx[1] ** 2)
        """
        self._assert_forward_smt_input(x=x)
        fns = get_solver_fns(x=x)
        _And = fns["And"]

        dhdx, dhdx_constraints, dhdx_symbolic_vars = self._h.gradient_smt(x=x)
        hx, hx_constraints, hx_symbolic_vars = self._h.forward_smt(x=x)
        norm = fns["RealVar"]("norm")
        symbolic_vars = dhdx_symbolic_vars + hx_symbolic_vars + [norm]

        norm_constraint = [
            norm * norm == dhdx[0, 0] ** 2 + dhdx[0, 1] ** 2,
            norm >= 0.0,
        ]
        sigma = norm * self._z_bound * self._k_function_smt(hx)

        self._assert_forward_smt_output(x=sigma)
        return sigma, hx_constraints + dhdx_constraints + norm_constraint, symbolic_vars

    def _assert_forward_input(self, x: torch.Tensor) -> None:
        state_dim = self._system.n_vars
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch input to be tensor, got {type(x)}"
        assert (
            len(x.shape) == 2
        ), f"expected batch input (batch, {state_dim}), got {x.shape}"
        assert (
            x.shape[1] == state_dim
        ), f"expected batch input (batch, {state_dim}), got {x.shape}"

    def _assert_forward_output(self, x: torch.Tensor) -> None:
        assert isinstance(
            x, torch.Tensor
        ), f"expected batch output to be tensor, got {type(x)}"
        assert len(x.shape) == 1, f"expected output of shape (batch,), got {x.shape}"

    def _assert_forward_smt_input(self, x: Iterable[SYMBOL]) -> None:
        state_dim = self._system.n_vars
        assert all(
            [isinstance(xi, SYMBOL) for xi in x]
        ), f"expected symbolic input, got {x}"
        assert (
            len(x) == state_dim
        ), f"expected {state_dim} state variables, got input of length {len(x)}"

    def _assert_forward_smt_output(self, x: Iterable[SYMBOL]) -> None:
        assert isinstance(x, SYMBOL), f"expected symbolic output, got {x}"

    def _k_function(self, hx: torch.Tensor) -> torch.Tensor:
        """
        It is a continuous, non-increasing function
        k: R≥0 → R with k(0) = 1

        From https://arxiv.org/pdf/2211.14364.pdf
        k(r) = 2 / (1 + exp(r))
        However, this is non polynomial (need dreal).

        So we use a polynomial approximation which is valid for r in [0, inf]
        """
        # return 2 / (1 + torch.exp(hx)) # z3 does not supports exp, try polynomial; also we can see what is the range of hx,
        return self._epsilon + 1 / (hx ** 2 + 1)

    def _k_function_smt(self, hx: SYMBOL) -> tuple[SYMBOL, Iterable[SYMBOL]]:
        """
        Instead of using exp, we use polynomial version which is valid for r in [0, inf]
        """
        # assert isinstance(hx, DRSYMBOL), f"expected dreals symbolic expression, got {hx}"
        # fns = get_solver_fns(x=[hx])
        # return 2 / (1 + fns["Exp"](hx))
        return self._epsilon + 1 / (hx ** 2 + 1)

    def save(self, *args, **kwargs):
        warnings.warn("Saving is not supported for hand-crafted models")

    @staticmethod
    def load(*args, **kwargs):
        warnings.warn("Loading is not supported for hand-crafted models")
