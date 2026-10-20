from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction

import numpy as np


@dataclass(frozen=True, slots=True)
class AffineSymmetry:
    rotation: np.ndarray
    translation: np.ndarray


def _linear_expression(node: ast.AST) -> tuple[tuple[Fraction, Fraction, Fraction], Fraction]:
    if isinstance(node, ast.Expression):
        return _linear_expression(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return (Fraction(0), Fraction(0), Fraction(0)), Fraction(str(node.value))
    if isinstance(node, ast.Name) and node.id in {"x", "y", "z"}:
        coefficients = [Fraction(0), Fraction(0), Fraction(0)]
        coefficients[("x", "y", "z").index(node.id)] = Fraction(1)
        return tuple(coefficients), Fraction(0)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        coefficients, constant = _linear_expression(node.operand)
        sign = Fraction(1) if isinstance(node.op, ast.UAdd) else Fraction(-1)
        return tuple(sign * value for value in coefficients), sign * constant
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        left_coefficients, left_constant = _linear_expression(node.left)
        right_coefficients, right_constant = _linear_expression(node.right)
        sign = Fraction(1) if isinstance(node.op, ast.Add) else Fraction(-1)
        return (
            tuple(
                left + sign * right
                for left, right in zip(left_coefficients, right_coefficients, strict=True)
            ),
            left_constant + sign * right_constant,
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left_coefficients, left_constant = _linear_expression(node.left)
        right_coefficients, right_constant = _linear_expression(node.right)
        if any(left_coefficients) and any(right_coefficients):
            raise ValueError("Symmetry operation is not affine.")
        if any(left_coefficients):
            return tuple(value * right_constant for value in left_coefficients), left_constant * right_constant
        if any(right_coefficients):
            return tuple(value * left_constant for value in right_coefficients), right_constant * left_constant
        return (Fraction(0), Fraction(0), Fraction(0)), left_constant * right_constant
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        numerator_coefficients, numerator_constant = _linear_expression(node.left)
        denominator_coefficients, denominator_constant = _linear_expression(node.right)
        if any(denominator_coefficients) or denominator_constant == 0:
            raise ValueError("Symmetry-operation divisor must be a nonzero constant.")
        return (
            tuple(value / denominator_constant for value in numerator_coefficients),
            numerator_constant / denominator_constant,
        )
    raise ValueError("Unsupported expression in symmetry operation.")


def parse_affine_operation(operation: str) -> AffineSymmetry:
    parts = operation.strip().strip("'\"").lower().replace("−", "-").split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid symmetry operation: {operation}")
    rows: list[tuple[Fraction, Fraction, Fraction]] = []
    translations: list[Fraction] = []
    for expression in parts:
        coefficients, constant = _linear_expression(ast.parse(expression.strip(), mode="eval"))
        if any(value.denominator != 1 for value in coefficients):
            raise ValueError("Symmetry rotation must have integral coefficients.")
        rows.append(coefficients)
        translations.append(constant % 1)
    rotation = np.asarray([[int(value) for value in row] for row in rows], dtype=int)
    determinant = float(np.linalg.det(rotation))
    if not np.isclose(abs(determinant), 1.0):
        raise ValueError("Symmetry rotation must be unimodular.")
    translation = np.asarray([float(value) for value in translations], dtype=float)
    rotation.setflags(write=False)
    translation.setflags(write=False)
    return AffineSymmetry(rotation, translation)
