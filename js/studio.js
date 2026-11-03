import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const COLORS={H3StudioPrompt:["#243954","#101b2b"],H3StudioReferences:["#25493f","#132923"],
 H3StudioControlVideo:["#4c3b27","#2a2116"],H3StudioEngine:["#344775","#17213a"],
 H3StudioSaveVideo:["#274752","#13252d"]};
const style=document.createElement("style");
style.textContent=".h3-studio-tools{font:12px/1.5 system-ui;color:#cbd8ea;padding:9px;box-sizing:border-box;overflow:hidden;height:100%}.h3-studio-tools button{background:#294e73;color:#f0f6ff;border:1px solid #567ca0;border-radius:7px;padding:7px 12px;font:inherit;cursor:pointer}.h3-studio-tools button:disabled{opacity:.45}.h3-studio-status{white-space:pre-wrap;overflow-wrap:anywhere;color:#aebfd4;margin:6px 0}.h3-studio-tools video{width:100%;max-height:250px;display:block;background:#080d15;border-radius:7px;margin-top:8px}.h3-studio-tools .error{color:#ffa4a4}";
document.head.append(style);

function widget(node,name){return node.widgets?.find(w=>w.name===name);}
function change(node,name,value){
 const w=widget(node,name);if(!w)return;
 w.value=value;w.callback?.(value);node.setDirtyCanvas(true,true);app.graph.change();
}
function tools(node,height){
 const root=document.createElement("div");root.className="h3-studio-tools";
 root.addEventListener("pointerdown",e=>e.stopPropagation());
 const status=document.createElement("div");status.className="h3-studio-status";root.append(status);
 const dom=node.addDOMWidget("studio_tools","h3-studio-tools",root,{
  serialize:false,hideOnZoom:false,getMinHeight:()=>height,getMaxHeight:()=>height});
 dom.serialize=false;
 return {root,status};
}
function button(root,label,action){
 const b=document.createElement("button");b.textContent=label;
 b.onclick=async()=>{b.disabled=true;try{await action();}finally{b.disabled=false;}};
 root.prepend(b);return b;
}
function choose(accept){
 return new Promise(resolve=>{
  const input=document.createElement("input");input.type="file";input.accept=accept;
  input.onchange=()=>resolve(input.files?.[0]??null);input.oncancel=()=>resolve(null);input.click();
 });
}
function statusEvents(node,status){
 const old=node.onExecuted;
 node.onExecuted=function(result){
  old?.apply(this,arguments);
  if(result?.studio_status)status.textContent=result.studio_status.join("\n");
 };
}
function install(node){
 if(node._h3StudioInstalled||!COLORS[node.comfyClass])return;
 node._h3StudioInstalled=true;
 [node.color,node.bgcolor]=COLORS[node.comfyClass];
 if(node.comfyClass==="H3StudioPrompt"){
  const {root,status}=tools(node,94);status.textContent="TXT / Markdown 等文本 · 自动或指定编码 · 严格解码";
  let busy=false;
  button(root,"选择提示词文件",async()=>{
   const file=await choose(".txt,.md,.markdown,.text,.rst,.log,.json,.yaml,.yml,.csv,.srt");
   if(!file)return;busy=true;
   try{
    const form=new FormData();form.append("file",file);
    const response=await api.fetchApi("/h3_studio/upload_text",{method:"POST",body:form});
    if(!response.ok)throw new Error(await response.text());
    const result=await response.json();
    change(node,"text_file",result.file);change(node,"source","文本文件");
    status.textContent="已选择 "+result.name+"；运行时按指定编码读取。";status.classList.remove("error");
   }catch(error){status.textContent=error.message;status.classList.add("error");}
   finally{busy=false;}
  });
  widget(node,"text_file").beforeQueued=()=>{if(busy)throw new Error("提示词文件仍在上传。");};
  statusEvents(node,status);
 }else if(node.comfyClass==="H3StudioControlVideo"){
  const {root,status}=tools(node,305);
  const video=document.createElement("video");video.controls=true;video.preload="metadata";root.append(video);
  function render(){
   const file=widget(node,"file").value;
   const enabled=file&&file!=="（不使用）";
   video.style.display=enabled?"block":"none";
   status.textContent=enabled?"输入视频预览 · 只有启用 FunControl 时才提取姿态":"未选择控制视频；FunControl 关闭时无需提供。";
   if(enabled){
    const normalized=file.replaceAll("\\","/");const slash=normalized.lastIndexOf("/");
    const query=new URLSearchParams({filename:normalized.slice(slash+1),subfolder:normalized.slice(0,slash<0?0:slash),type:"input"});
    const url=api.apiURL("/view?"+query);
    if(video.getAttribute("src")!==url)video.src=url;
   }else video.removeAttribute("src");
  }
  let busy=false;
  button(root,"选择 / 上传控制视频",async()=>{
   const file=await choose("video/*,.mp4,.mkv,.mov,.webm,.avi");
   if(!file)return;busy=true;
   try{
    const form=new FormData();form.append("image",file);form.append("type","input");form.append("overwrite","false");
    const response=await api.fetchApi("/upload/image",{method:"POST",body:form});
    if(!response.ok)throw new Error(await response.text());
    const result=await response.json();const name=(result.subfolder?result.subfolder+"/":"")+result.name;
    const w=widget(node,"file");
    if(Array.isArray(w.options.values)&&!w.options.values.includes(name))w.options.values.push(name);
    change(node,"file",name);render();
   }catch(error){status.textContent=error.message;status.classList.add("error");}
   finally{busy=false;}
  });
  const w=widget(node,"file");const old=w.callback;
  w.callback=function(...a){old?.apply(this,a);render();};
  w.beforeQueued=()=>{if(busy)throw new Error("控制视频仍在上传。");};
  node._studioRender=render;render();
 }else if(node.comfyClass==="H3StudioEngine"){
  const {status}=tools(node,76);
  const render=()=>{
   const fast=!!widget(node,"enable_fasth3").value;
   const fun=!!widget(node,"enable_funcontrol").value;
   const lora=!!widget(node,"enable_lora").value;
   const target=Math.max(5,Math.round(Number(widget(node,"duration_seconds").value)*24));
   const frames=target+(5-target%17+17)%17;
   status.textContent=(fast?"FastH3 模式 · LoRA / FunControl 不参与本次生成":
    "MiniMax H3 模式"+(lora?" · 加速 LoRA":"")+(fun?" · FunControl":" · 无姿态控制"))+
    "\n"+frames+" 帧 · "+(frames/24).toFixed(2)+" 秒 · 关闭的模型分支不加载。";
  };
  for(const name of ["enable_fasth3","enable_funcontrol","enable_lora","duration_seconds"]){
   const w=widget(node,name);const old=w.callback;w.callback=function(...a){old?.apply(this,a);render();};
  }
  node._studioRender=render;render();
 }else if(node.comfyClass==="H3StudioSaveVideo"){
  const {status}=tools(node,68);
  status.textContent="目录留空使用 ComfyUI 官方 output；也可填写绝对路径或 output 下的子目录。";
  statusEvents(node,status);
 }
}
app.registerExtension({
 name:"h3.studio.panel",
 nodeCreated:install,
 afterConfigureGraph(){for(const n of app.graph._nodes)n._studioRender?.();}
});
