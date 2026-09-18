function toolKey(tool) {
    return [tool.name, tool.path, tool.version].join("|");
}
export function compareRuntimeIdentity(a, b) {
    const all = [...a.tools, ...b.tools];
    if (all.some((tool) => tool.resolution === "UNKNOWN"))
        return "UNKNOWN";
    if (a.tools.length !== b.tools.length)
        return "DIFFERENT";
    const left = a.tools.map(toolKey).sort();
    const right = b.tools.map(toolKey).sort();
    return left.every((value, index) => value === right[index]) ? "MATCH" : "DIFFERENT";
}
