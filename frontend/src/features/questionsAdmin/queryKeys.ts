export const questionsModuleKeys = {
  root: ["questions", "module"] as const,
  list: (testId: number, moduleId: number) =>
    [...questionsModuleKeys.root, "list", testId, moduleId] as const,
};
