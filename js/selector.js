// H3 Studio reference selection UI.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ACCEPT, LABELS, LIMITS, counts, planFiles, readSelection, toggleAll } from "./selector_state.mjs";

const NAME = "H3StudioReferences";
const CSS = `
.h3-ref-ui,.h3-ref-dialog{font:13px/1.45 system-ui,sans-serif;color:var(--base-foreground,#eee);box-sizing:border-box}
.h3-ref-ui{padding:6px 10px;background:var(--comfy-menu-bg,#242424);border-radius:6px;overflow:hidden;height:100%}
.h3-ref-toolbar{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.h3-ref-ui button,.h3-ref-dialog button{font:inherit;color:inherit;background:var(--secondary-background,#383838);border:1px solid var(--border-default,#555);border-radius:5px;padding:6px 10px;cursor:pointer}
.h3-ref-ui button:disabled,.h3-ref-dialog button:disabled{opacity:.45;cursor:default}
.h3-ref-ui .primary,.h3-ref-dialog .primary{background:#315778;border-color:#5d8ca9}
.h3-ref-summary{font-size:12px;color:var(--muted-foreground,#bbb);margin:7px 0;overflow-wrap:anywhere}
.h3-ref-summary.error{color:#ff9999}.h3-ref-sound{display:flex;align-items:center;gap:7px;font-size:12px}
.h3-ref-ui input,.h3-ref-dialog input{accent-color:#6aa7d4}
.h3-ref-dialog{width:min(900px,92vw);max-height:88vh;overflow:auto;border:1px solid #666;border-radius:12px;padding:20px;background:var(--base-background,#242424);box-shadow:0 20px 70px #0008}
.h3-ref-dialog::backdrop{background:#0009}.h3-ref-dialog h2{font-size:18px;margin:0 0 6px}.h3-ref-dialog p{margin:5px 0 14px;color:#bbb}
.h3-ref-columns{display:grid;grid-template-columns:1fr 1fr;gap:16px}.h3-ref-group{border:1px solid #505050;border-radius:8px;padding:10px;margin-bottom:12px}
.h3-ref-group h3{font-size:13px;margin:0 0 8px}.h3-ref-slot{display:flex;align-items:center;gap:6px;min-height:36px;border-top:1px solid #444;padding:4px 0}
.h3-ref-slot.disabled{opacity:.55}.h3-ref-slot .port{font-size:11px;color:#aaa;width:18px;flex:none}.h3-ref-slot .filename{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.h3-ref-slot button{padding:3px 6px;font-size:11px}.h3-ref-dialog .footer{border-top:1px solid #555;padding-top:12px;margin-top:6px;display:flex;justify-content:space-between;gap:12px;align-items:center}
.h3-ref-drop{outline:2px dashed #6aa7d4;outline-offset:-3px}
`;

function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
}

function install(node) {
    if (node._h3Selector) return;
    const manifest = node.widgets.find(widget => widget.name === "manifest");
    const sound = node.widgets.find(widget => widget.name === "use_video_audio");
    manifest.hidden = sound.hidden = true;
    const root = element("div", "h3-ref-ui");
    root.dataset.h3Selector = String(node.id);
    let busy = false, message = "", dialog = null;
    let dialogRows, dialogSummary, dialogSound, dialogBar, dialogDone;
    const toolbar = element("div", "h3-ref-toolbar");
    const summary = element("div", "h3-ref-summary");
    const soundLabel = element("label", "h3-ref-sound");
    const soundCheck = document.createElement("input");
    soundCheck.type = "checkbox";
    soundLabel.append(soundCheck, document.createTextNode("使用视频自带音轨"));
    root.append(toolbar, summary, soundLabel);

    const state = () => readSelection(manifest.value);
    function save(value) {
        manifest.value = JSON.stringify(value);
        manifest.callback?.(manifest.value);
        node.setDirtyCanvas(true, true);
        app.graph.change();
        message = "";
        render();
    }
    function setSound(value) {
        sound.value = value;
        sound.callback?.(value);
        node.setDirtyCanvas(true, true);
        app.graph.change();
        render();
    }
    soundCheck.addEventListener("change", () => setSound(soundCheck.checked));
    function button(label, action, primary = false) {
        const item = element("button", primary ? "primary" : "", label);
        item.type = "button";
        item.addEventListener("click", action);
        return item;
    }
    function attachDrop(target) {
        target.addEventListener("dragover", event => {
            event.preventDefault(); event.stopPropagation(); target.classList.add("h3-ref-drop");
        });
        target.addEventListener("dragleave", () => target.classList.remove("h3-ref-drop"));
        target.addEventListener("drop", event => {
            event.preventDefault(); event.stopPropagation(); target.classList.remove("h3-ref-drop");
            upload(Array.from(event.dataTransfer.files));
        });
    }
    function choose(target = null) {
        if (busy) return;
        const input = document.createElement("input");
        input.type = "file";
        input.multiple = !target;
        input.accept = target ? ACCEPT[target.kind] : Object.values(ACCEPT).join(",");
        input.hidden = true;
        (dialog ?? root).append(input);
        input.addEventListener("change", () => {
            const files = Array.from(input.files);
            input.remove();
            upload(files, target);
        }, { once: true });
        input.addEventListener("cancel", () => input.remove(), { once: true });
        input.click();
    }
    async function upload(files, target = null) {
        if (busy || !files.length) return;
        try {
            const current = state();
            const plan = planFiles(current, files, target);
            busy = true;
            const draft = structuredClone(current);
            for (const [index, entry] of plan.entries()) {
                message = `正在添加 ${index + 1}/${plan.length}：${entry.file.name}`;
                render();
                const form = new FormData();
                form.append("image", entry.file);
                form.append("type", "input");
                form.append("subfolder", "h3_references");
                const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
                if (!response.ok) throw new Error(`上传失败（${response.status}）：${entry.file.name}`);
                const saved = await response.json();
                draft[entry.kind][entry.index] = {
                    path: saved.subfolder ? `${saved.subfolder}/${saved.name}` : saved.name, enabled: true,
                };
            }
            busy = false;
            save(draft);
            openDialog();
        } catch (error) {
            busy = false;
            message = `${error.message}；本次批量选择未应用，原清单保留。`;
            render();
        }
    }
    function drawGroup(kind, current) {
        const group = element("section", "h3-ref-group");
        group.append(element("h3", "", `${LABELS[kind]} · ${counts(current)[kind]}/${LIMITS[kind]}`));
        current[kind].forEach((entry, index) => {
            const port = `${kind}_${index + 1}`;
            const row = element("div", `h3-ref-slot${entry && !entry.enabled ? " disabled" : ""}`);
            const check = document.createElement("input");
            check.type = "checkbox";
            check.checked = !!entry?.enabled;
            check.disabled = busy || !entry;
            check.setAttribute("aria-label", `启用 ${port}`);
            check.addEventListener("change", () => {
                const changed = state();
                changed[kind][index].enabled = check.checked;
                save(changed);
            });
            const name = element("span", "filename", entry ? entry.path.split("/").pop() : "未选择");
            name.title = entry?.path ?? "未选择";
            const pick = button(entry ? "更换" : "选择", () => choose({ kind, index }));
            pick.setAttribute("aria-label", `选择 ${port}`);
            pick.disabled = busy;
            const remove = button("×", () => {
                const changed = state(); changed[kind][index] = null; save(changed);
            });
            remove.setAttribute("aria-label", `移除 ${port}`);
            remove.disabled = busy || !entry;
            row.append(check, element("span", "port", String(index + 1)), name, pick, remove);
            group.append(row);
        });
        return group;
    }
    function openDialog() {
        if (dialog) { render(); return; }
        dialog = element("dialog", "h3-ref-dialog");
        dialog.setAttribute("aria-label", "参考素材管理（9/3/3）");
        dialog.append(element("h2", "", "参考素材管理 · 9 / 3 / 3"),
            element("p", "", "可一次选择多张图片、多段音频和视频。取消勾选只停用本次参考，不删除文件。"));
        const bar = element("div", "h3-ref-toolbar");
        dialogBar = bar;
        bar.append(button("批量添加文件", () => choose(), true),
            button("全选", () => save(toggleAll(state(), true))),
            button("全不选", () => save(toggleAll(state(), false))));
        dialogRows = element("div", "h3-ref-columns");
        dialogSummary = element("div", "h3-ref-summary");
        const footer = element("div", "footer");
        const label = element("label", "h3-ref-sound");
        dialogSound = document.createElement("input");
        dialogSound.type = "checkbox";
        dialogSound.addEventListener("change", () => setSound(dialogSound.checked));
        label.append(dialogSound, document.createTextNode("使用视频自带音轨"));
        dialogDone = button("完成", () => dialog.close(), true);
        footer.append(label, dialogDone);
        dialog.append(bar, dialogRows, dialogSummary,
            element("p", "", "启用文件总数最多 12。视频音轨＋独立音频合计最多 3 段、15 秒；具体时长由后面的校验节点检查。"), footer);
        dialog.addEventListener("close", () => { dialog.remove(); dialog = null; }, { once: true });
        document.body.append(dialog);
        attachDrop(dialog);
        render();
        dialog.showModal();
    }
    function render() {
        try {
            const current = state(), count = counts(current);
            const text = message || `图像 ${count.image}/9 · 音频 ${count.audio}/3 · 视频 ${count.video}/3 · 已启用 ${count.total}/12`;
            summary.textContent = text;
            summary.classList.toggle("error", !!message && !busy || count.total > 12);
            soundCheck.checked = !!sound.value;
            soundCheck.disabled = busy;
            toolbar.querySelectorAll("button").forEach(item => { item.disabled = busy; });
            if (dialog) {
                dialogSummary.textContent = count.total > 12 ? `${text}；请取消勾选至少 ${count.total - 12} 个参考。` : text;
                dialogSummary.classList.toggle("error", !!message && !busy || count.total > 12);
                const right = element("div");
                right.append(drawGroup("audio", current), drawGroup("video", current));
                dialogRows.replaceChildren(drawGroup("image", current), right);
                dialogSound.checked = !!sound.value;
                dialogSound.disabled = busy;
                dialogBar.querySelectorAll("button").forEach(item => { item.disabled = busy; });
                dialogDone.disabled = busy;
            }
        } catch (error) {
            summary.textContent = error.message;
            summary.classList.add("error");
        }
    }
    toolbar.append(button("批量添加文件", () => choose(), true), button("管理参考", openDialog));
    root.addEventListener("pointerdown", event => event.stopPropagation());
    attachDrop(root);
    const dom = node.addDOMWidget("reference_selector", "h3-reference-selector", root, {
        serialize: false, hideOnZoom: false, getMinHeight: () => 126, getMaxHeight: () => 126,
    });
    dom.serialize = false;
    manifest.beforeQueued = () => { if (busy) throw new Error("参考素材仍在上传，请等待完成后再运行。"); };
    node.setSize([Math.max(node.size[0], 500), Math.max(node.size[1], 235)]);
    node._h3Selector = { render };
    const previousRemoved = node.onRemoved;
    node.onRemoved = function (...args) {
        dialog?.close();
        return previousRemoved?.apply(this, args);
    };
    render();
}

app.registerExtension({
    name: "h3.studio.reference.selector",
    setup() {
        const style = element("style"); style.textContent = CSS; document.head.append(style);
    },
    nodeCreated(node) { if (node.comfyClass === NAME) install(node); },
    afterConfigureGraph() {
        for (const node of app.graph._nodes) if (node.comfyClass === NAME) node._h3Selector?.render();
    },
});
