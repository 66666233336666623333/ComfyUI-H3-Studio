from comfy_api.latest import ComfyExtension
from .nodes import STUDIO_NODES
from .routes import register_routes
from .reference.selector import H3StudioReferenceLoader
from .reference.conditioning import H3StudioReferenceConditioning

WEB_DIRECTORY = "./js"

class H3StudioExtension(ComfyExtension):
    async def get_node_list(self):
        return [*STUDIO_NODES, H3StudioReferenceLoader, H3StudioReferenceConditioning]

    async def on_load(self):
        register_routes()

async def comfy_entrypoint():
    return H3StudioExtension()
