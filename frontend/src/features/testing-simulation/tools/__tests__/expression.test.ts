import { describe, expect, it } from "vitest";
import { evaluate, tryEvaluate } from "../calculator/expression";

describe("expression evaluator", () => {
  it("respects operator precedence", () => {
    expect(evaluate("2+3*4")).toBe(14);
    expect(evaluate("(2+3)*4")).toBe(20);
    expect(evaluate("10-2-3")).toBe(5); // left assoc
  });

  it("handles powers (right-associative) and unary minus", () => {
    expect(evaluate("2^3^2")).toBe(512); // 2^(3^2)
    expect(evaluate("-2^2")).toBe(-4); // -(2^2)
    expect(evaluate("3*-2")).toBe(-6);
  });

  it("supports functions in radians and degrees", () => {
    expect(evaluate("sin(0)")).toBeCloseTo(0, 10);
    expect(evaluate("cos(0)")).toBe(1);
    expect(evaluate("sin(90)", { degrees: true })).toBeCloseTo(1, 10);
    expect(evaluate("sqrt(16)")).toBe(4);
    expect(evaluate("log(1000)")).toBeCloseTo(3, 10);
    expect(evaluate("ln(e)")).toBeCloseTo(1, 10);
  });

  it("handles constants, factorial and percent", () => {
    expect(evaluate("pi")).toBeCloseTo(Math.PI, 10);
    expect(evaluate("5!")).toBe(120);
    expect(evaluate("50%")).toBe(0.5);
    expect(evaluate("200*10%")).toBe(20);
  });

  it("throws on malformed / unsafe input (no eval)", () => {
    expect(() => evaluate("2+")).toThrow();
    expect(() => evaluate("1/0")).toThrow();
    expect(() => evaluate("alert(1)")).toThrow();
    expect(() => evaluate("2**3")).toThrow();
    expect(() => evaluate("")).toThrow();
  });

  it("tryEvaluate returns a string or 'Error' and never throws", () => {
    expect(tryEvaluate("2+2")).toBe("4");
    expect(tryEvaluate("bad(")).toBe("Error");
  });
});
