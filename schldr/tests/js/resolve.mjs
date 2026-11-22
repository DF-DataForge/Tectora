export async function resolve(specifier, context, nextResolve) {
    if (specifier.startsWith(".") && !/\.(m?js|json)$/.test(specifier)) {
        return nextResolve(`${specifier}.js`, context);
    }
    return nextResolve(specifier, context);
}
