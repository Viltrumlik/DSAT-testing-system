declare module "katex/contrib/auto-render" {
  interface DelimiterSpec {
    left: string;
    right: string;
    display: boolean;
  }
  interface RenderMathInElementOptions {
    delimiters?: readonly DelimiterSpec[];
    throwOnError?: boolean;
    trust?: boolean;
    ignoredTags?: string[];
    ignoredClasses?: string[];
    errorCallback?: (msg: string, err: Error) => void;
  }
  function renderMathInElement(
    elem: HTMLElement,
    options?: RenderMathInElementOptions,
  ): void;
  export default renderMathInElement;
}
