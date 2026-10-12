"""Roots extension. Geometry can also be imported outside Blender."""

def register():
    from . import addon
    addon.register()


def unregister():
    from . import addon
    addon.unregister()


def rebuild_all(scene):
    from .addon import rebuild_all as rebuild
    return rebuild(scene)
