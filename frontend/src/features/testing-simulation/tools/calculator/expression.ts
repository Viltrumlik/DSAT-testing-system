/**
 * Safe math-expression evaluator (no `eval`). Recursive-descent parser over a
 * tokenizer. Pure and unit-tested. Powers the Calculator tool only.
 *
 * Supports: + - * / ^, unary -, parentheses, factorial (!), percent (50% → 0.5),
 * functions sin cos tan asin acos atan sqrt cbrt ln log abs exp, constants pi/e.
 */

export interface EvalOptions {
  /** Interpret trig args/results in degrees instead of radians. */
  degrees?: boolean;
}

type Tok = { t: "num"; v: number } | { t: "op"; v: string } | { t: "fn"; v: string } | { t: "const"; v: string } | { t: "paren"; v: "(" | ")" };

const FUNCS = new Set(["sin", "cos", "tan", "asin", "acos", "atan", "sqrt", "cbrt", "ln", "log", "abs", "exp"]);

function tokenize(input: string): Tok[] {
  const s = input.replace(/\s+/g, "");
  const out: Tok[] = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if ((c >= "0" && c <= "9") || c === ".") {
      let j = i + 1;
      while (j < s.length && /[0-9.]/.test(s[j])) j++;
      const num = Number(s.slice(i, j));
      if (!Number.isFinite(num)) throw new Error("Invalid number");
      out.push({ t: "num", v: num });
      i = j;
    } else if (/[a-z]/i.test(c)) {
      let j = i + 1;
      while (j < s.length && /[a-z]/i.test(s[j])) j++;
      const word = s.slice(i, j).toLowerCase();
      if (FUNCS.has(word)) out.push({ t: "fn", v: word });
      else if (word === "pi" || word === "e") out.push({ t: "const", v: word });
      else throw new Error(`Unknown name: ${word}`);
      i = j;
    } else if ("+-*/^!%".includes(c)) {
      out.push({ t: "op", v: c });
      i++;
    } else if (c === "(" || c === ")") {
      out.push({ t: "paren", v: c });
      i++;
    } else {
      throw new Error(`Unexpected character: ${c}`);
    }
  }
  return out;
}

class Parser {
  private pos = 0;
  constructor(private toks: Tok[], private opts: EvalOptions) {}

  parse(): number {
    const v = this.expr();
    if (this.pos < this.toks.length) throw new Error("Unexpected trailing input");
    return v;
  }
  private peek(): Tok | undefined {
    return this.toks[this.pos];
  }
  private expr(): number {
    let v = this.term();
    for (let t = this.peek(); t && t.t === "op" && (t.v === "+" || t.v === "-"); t = this.peek()) {
      this.pos++;
      v = t.v === "+" ? v + this.term() : v - this.term();
    }
    return v;
  }
  private term(): number {
    let v = this.unary();
    for (let t = this.peek(); t && t.t === "op" && (t.v === "*" || t.v === "/"); t = this.peek()) {
      this.pos++;
      const rhs = this.unary();
      if (t.v === "/" && rhs === 0) throw new Error("Division by zero");
      v = t.v === "*" ? v * rhs : v / rhs;
    }
    return v;
  }
  private unary(): number {
    // Unary minus binds looser than ^, so -2^2 = -(2^2) = -4.
    const t = this.peek();
    if (t && t.t === "op" && (t.v === "-" || t.v === "+")) {
      this.pos++;
      const v = this.unary();
      return t.v === "-" ? -v : v;
    }
    return this.power();
  }
  private power(): number {
    const base = this.postfix();
    const t = this.peek();
    if (t && t.t === "op" && t.v === "^") {
      this.pos++;
      return Math.pow(base, this.unary()); // right-assoc; exponent may be signed
    }
    return base;
  }
  private postfix(): number {
    let v = this.primary();
    for (let t = this.peek(); t && t.t === "op" && (t.v === "!" || t.v === "%"); t = this.peek()) {
      this.pos++;
      v = t.v === "!" ? factorial(v) : v / 100;
    }
    return v;
  }
  private primary(): number {
    const t = this.peek();
    if (!t) throw new Error("Unexpected end of input");
    if (t.t === "num") {
      this.pos++;
      return t.v;
    }
    if (t.t === "const") {
      this.pos++;
      return t.v === "pi" ? Math.PI : Math.E;
    }
    if (t.t === "fn") {
      this.pos++;
      this.expect("(");
      const arg = this.expr();
      this.expect(")");
      return this.applyFn(t.v, arg);
    }
    if (t.t === "paren" && t.v === "(") {
      this.pos++;
      const v = this.expr();
      this.expect(")");
      return v;
    }
    throw new Error("Expected a value");
  }
  private expect(p: "(" | ")") {
    const t = this.peek();
    if (!t || t.t !== "paren" || t.v !== p) throw new Error(`Expected '${p}'`);
    this.pos++;
  }
  private applyFn(name: string, x: number): number {
    const toRad = (v: number) => (this.opts.degrees ? (v * Math.PI) / 180 : v);
    const fromRad = (v: number) => (this.opts.degrees ? (v * 180) / Math.PI : v);
    switch (name) {
      case "sin": return Math.sin(toRad(x));
      case "cos": return Math.cos(toRad(x));
      case "tan": return Math.tan(toRad(x));
      case "asin": return fromRad(Math.asin(x));
      case "acos": return fromRad(Math.acos(x));
      case "atan": return fromRad(Math.atan(x));
      case "sqrt": if (x < 0) throw new Error("sqrt of negative"); return Math.sqrt(x);
      case "cbrt": return Math.cbrt(x);
      case "ln": if (x <= 0) throw new Error("ln domain"); return Math.log(x);
      case "log": if (x <= 0) throw new Error("log domain"); return Math.log10(x);
      case "abs": return Math.abs(x);
      case "exp": return Math.exp(x);
      default: throw new Error(`Unknown function ${name}`);
    }
  }
}

function factorial(n: number): number {
  if (n < 0 || !Number.isInteger(n)) throw new Error("factorial needs a non-negative integer");
  if (n > 170) throw new Error("factorial too large");
  let r = 1;
  for (let k = 2; k <= n; k++) r *= k;
  return r;
}

/** Evaluate an expression string. Throws `Error` on any malformed input. */
export function evaluate(input: string, opts: EvalOptions = {}): number {
  if (!input.trim()) throw new Error("Empty expression");
  const result = new Parser(tokenize(input), opts).parse();
  if (!Number.isFinite(result)) throw new Error("Result is not finite");
  return result;
}

/** Convenience wrapper returning a display string or "Error". */
export function tryEvaluate(input: string, opts: EvalOptions = {}): string {
  try {
    const v = evaluate(input, opts);
    return String(Number.parseFloat(v.toPrecision(12)));
  } catch {
    return "Error";
  }
}
