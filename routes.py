"""Text uploads remain local and are stored separately from reference media."""
import uuid
from pathlib import Path
from aiohttp import web
import folder_paths
from server import PromptServer
from .core import MAX_TEXT_BYTES, TEXT_EXTENSIONS

def register_routes():
    @PromptServer.instance.routes.post("/h3_studio/upload_text")
    async def upload_text(request):
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != "file" or not part.filename:
            raise web.HTTPBadRequest(text="请选择文本文件。")
        filename = Path(part.filename.replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in TEXT_EXTENSIONS:
            raise web.HTTPBadRequest(text="不支持此文本格式。")
        data = bytearray()
        while chunk := await part.read_chunk():
            data.extend(chunk)
            if len(data) > MAX_TEXT_BYTES:
                raise web.HTTPRequestEntityTooLarge(max_size=MAX_TEXT_BYTES, actual_size=len(data))
        directory = Path(folder_paths.get_input_directory()) / "h3_studio_prompts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{Path(filename).stem}_{uuid.uuid4().hex[:10]}{suffix}"
        with path.open("xb") as stream:
            stream.write(data)
        return web.json_response({"file": path.relative_to(folder_paths.get_input_directory()).as_posix(),
                                  "name": filename, "bytes": len(data)})
