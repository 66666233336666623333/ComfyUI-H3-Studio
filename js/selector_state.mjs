export const LIMITS = Object.freeze({ image: 9, audio: 3, video: 3 });
export const LABELS = Object.freeze({ image: "图像", audio: "音频", video: "视频" });
const EXTENSIONS = {
    image: ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "avif", "gif", "apng"],
    audio: ["wav", "mp3", "flac", "m4a", "aac", "ogg", "opus", "aif", "aiff", "wma"],
    video: ["mp4", "mkv", "mov", "webm", "avi", "m4v", "mpeg", "mpg"],
};
export const ACCEPT = Object.fromEntries(Object.entries(EXTENSIONS).map(([kind, extensions]) =>
    [kind, extensions.map(extension => `.${extension}`).join(",")]));

export function emptySelection() {
    return Object.fromEntries(Object.entries(LIMITS).map(([kind, size]) => [kind, Array(size).fill(null)]));
}

export function readSelection(value) {
    const raw = JSON.parse(value);
    if (!raw || Array.isArray(raw) || typeof raw !== "object" || Object.keys(raw).some(key => !(key in LIMITS))) {
        throw new Error("参考清单格式无效");
    }
    const state = emptySelection();
    for (const [kind, maximum] of Object.entries(LIMITS)) {
        const entries = raw[kind] ?? [];
        if (!Array.isArray(entries) || entries.length > maximum) throw new Error(`${LABELS[kind]}最多 ${maximum} 个位置`);
        entries.forEach((entry, i) => {
            if (entry === null) return;
            if (!entry || typeof entry.path !== "string" ||
                (entry.enabled !== undefined && typeof entry.enabled !== "boolean")) throw new Error("参考条目无效");
            state[kind][i] = { path: entry.path, enabled: entry.enabled ?? true };
        });
    }
    return state;
}

export function fileKind(name) {
    const extension = name.split(".").pop().toLowerCase();
    const kind = Object.keys(EXTENSIONS).find(key => EXTENSIONS[key].includes(extension));
    if (!kind) throw new Error(`不支持的素材类型：${name}`);
    return kind;
}

export function planFiles(state, files, target = null) {
    if (target) {
        if (files.length !== 1 || fileKind(files[0].name) !== target.kind) throw new Error(`请选择一个${LABELS[target.kind]}文件`);
        return [{ ...target, file: files[0] }];
    }
    const free = Object.fromEntries(Object.keys(LIMITS).map(kind =>
        [kind, state[kind].flatMap((entry, index) => entry ? [] : [index])]));
    return files.map(file => {
        const kind = fileKind(file.name);
        const index = free[kind].shift();
        if (index === undefined) throw new Error(`${LABELS[kind]}位置不足，最多 ${LIMITS[kind]} 个；请先移除旧素材。`);
        return { kind, index, file };
    });
}

export function counts(state) {
    const enabled = Object.fromEntries(Object.keys(LIMITS).map(kind =>
        [kind, state[kind].filter(entry => entry?.enabled && entry.path).length]));
    return { ...enabled, total: Object.values(enabled).reduce((a, b) => a + b, 0) };
}

export function toggleAll(state, enabled) {
    return Object.fromEntries(Object.entries(state).map(([kind, entries]) =>
        [kind, entries.map(entry => entry ? { ...entry, enabled } : null)]));
}
