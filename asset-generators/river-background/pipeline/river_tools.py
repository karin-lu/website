"""Install this file as a Blender add-on, or Run Script from the delivered .blend."""
bl_info={'name':'River Background Tools','author':'Trisball','version':(1,1,0),
         'blender':(4,3,0),'location':'3D View > Sidebar > River','category':'Object'}
import importlib, json, os, subprocess, sys
from pathlib import Path
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

def core():
    path=bpy.context.scene.get('river_pipeline_path')
    if not path:
        path=str(Path(__file__).resolve().parent)
    if not (Path(path)/'river_core.py').exists():
        raise ValueError('Set scene river_pipeline_path to the pipeline folder')
    if path not in sys.path: sys.path.insert(0,path)
    return importlib.import_module('river_core')

def rock(context):
    ob=context.active_object
    if ob is None or ob.type!='MESH' or 'river_recipe' not in ob:
        raise ValueError('Select a generated rock mesh')
    return ob

class RIVER_OT_generate(bpy.types.Operator):
    bl_idname='river.generate'; bl_label='Create / Rebuild Rock'; bl_options={'REGISTER','UNDO'}
    mode: EnumProperty(items=[('CREATE','Create',''),('REBUILD','Rebuild',''),('VARIANT','New variant','')])
    preset: EnumProperty(items=[(x,x.title(),'') for x in ('terrace','pillar','wall','arch','distant')])
    seed: IntProperty(default=31,min=0)
    depth: FloatProperty(default=1.05,min=.02,max=5)
    fractures: FloatProperty(default=1.3,min=.5,max=30)
    weathering: FloatProperty(default=.25,min=0,max=1)
    detail: IntProperty(default=1000,min=200,max=10000)
    use_outline: BoolProperty(name='Use selected closed poly curve',default=False)

    def invoke(self,context,event):
        if self.mode!='CREATE':
            try:
                r=core().recipe_for(rock(context)); self.preset=r['preset']; p=r['params']
                self.seed=p['seed']; self.depth=p['depth']; self.fractures=p['slabsPerArea']
                self.weathering=p['weathering']; self.detail=p['faceBudget']
            except Exception as e:
                self.report({'ERROR'},str(e)); return {'CANCELLED'}
        self._target=context.active_object
        return context.window_manager.invoke_props_dialog(self,width=340)

    def draw(self,context):
        layout=self.layout
        for field in ('preset','seed','depth','fractures','weathering','detail'): layout.prop(self,field)
        if self.mode=='CREATE': layout.prop(self,'use_outline')
        layout.label(text='Builds in a separate process; your scene stays editable.')

    def execute(self,context):
        try:
            c=core(); self._target=getattr(self,'_target',context.active_object)
            recipe={'preset':self.preset}
            if self.mode!='CREATE':
                if self.mode=='REBUILD': c.assert_rebuildable(self._target)
                recipe=c.recipe_for(self._target)
            elif self.use_outline:
                ob=self._target
                if not ob or ob.type!='CURVE' or len(ob.data.splines)!=1:
                    raise ValueError('Select a single closed poly curve')
                sp=ob.data.splines[0]
                if sp.type!='POLY' or not sp.use_cyclic_u: raise ValueError('Use a closed POLY curve in local X/Z')
                if any(abs(p.co.y)>.001 for p in sp.points): raise ValueError('Keep outline in local X/Z')
                recipe['outline']=[[p.co.x,p.co.z] for p in sp.points]
            recipe['preset']=self.preset
            recipe.setdefault('params',{}).update(seed=self.seed,depth=self.depth,slabsPerArea=self.fractures,
                                                  weathering=self.weathering,faceBudget=self.detail)
            self._proc,self._out,self._log=c.launch_worker(recipe)
            self._timer=context.window_manager.event_timer_add(.5,window=context.window)
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'},'Generating rock; you can continue working. Esc cancels.')
            return {'RUNNING_MODAL'}
        except Exception as e:
            self.report({'ERROR'},str(e)); return {'CANCELLED'}

    def modal(self,context,event):
        if event.type=='ESC':
            # Cancellation only discards results. Worker can finish safely off-scene.
            self._log.close(); context.window_manager.event_timer_remove(self._timer)
            self.report({'INFO'},'Result discarded; existing scene unchanged.')
            return {'CANCELLED'}
        if event.type!='TIMER' or self._proc.poll() is None: return {'PASS_THROUGH'}
        self._log.close(); context.window_manager.event_timer_remove(self._timer)
        try:
            if self._proc.returncode: raise ValueError(core().worker_failure(self._out))
            c=core()
            if self.mode=='CREATE':
                ob=c.append_rock(self._out/'rock.blend',self.preset.title())
                ob.parent.location=context.scene.cursor.location
                if self.use_outline and self._target: ob.parent.matrix_world=self._target.matrix_world.copy()
            else:
                if self._target.name not in bpy.data.objects: raise ValueError('Target was deleted; result left in '+str(self._out))
                ob=c.replace_from_worker(self._target,self._out/'rock.blend',self.mode=='VARIANT')
            bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); context.view_layer.objects.active=ob
            self.report({'INFO'},'Rock ready. Surface attachments may need repositioning.')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'},str(e)); return {'CANCELLED'}

class RIVER_OT_action(bpy.types.Operator):
    bl_idname='river.action'; bl_label='River action'; bl_options={'REGISTER','UNDO'}
    action: StringProperty()
    def execute(self,context):
        try:
            c=core()
            if self.action=='PLAY': bpy.ops.screen.animation_play(); return {'FINISHED'}
            ob=rock(context)
            if self.action=='UNIQUE': c.make_unique(ob)
            elif self.action=='MANUAL': ob['river_mode']='MANUAL'
            elif self.action=='ASSEMBLE': c.assemble_sources(ob)
            elif self.action=='NEAR': c.change_depth(ob,32)
            elif self.action=='FAR': c.change_depth(ob,85)
            elif self.action=='OUTLINE':
                c.collection(c.RECIPES).hide_viewport=False
                guide=bpy.data.objects[ob['river_outline']]
                bpy.ops.object.select_all(action='DESELECT'); guide.select_set(True); context.view_layer.objects.active=guide
            elif self.action=='SOURCES':
                c.collection(c.RECIPES).hide_viewport=False
                bpy.data.collections[ob['river_sources']].hide_viewport=False
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'},str(e)); return {'CANCELLED'}

class RIVER_OT_preview(bpy.types.Operator):
    bl_idname='river.preview'; bl_label='River composition preview'
    mode: EnumProperty(items=[('COMPOSE','Foreground + background',''),
                              ('BACKGROUND','Background only',''),('CAMERA','Opening camera','')])
    def execute(self,context):
        try:
            c=core()
            if self.mode=='COMPOSE':
                c.foreground_preview(context.scene,True)
                c.opening_composition(context.scene)
            elif self.mode=='BACKGROUND': c.foreground_preview(context.scene,False)
            else: c.opening_composition(context.scene)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'},str(e)); return {'CANCELLED'}

class RIVER_OT_export(bpy.types.Operator):
    bl_idname='river.export'; bl_label='Export Saved Background'
    plate_only: BoolProperty(default=False)
    def execute(self,context):
        try:
            if context.scene.get('river_layer_editor_state'):
                raise ValueError('Use Composition preview to finish outline editing, then save before exporting')
            if context.scene.get('river_layer_editor_busy'):
                raise ValueError('Wait for the layer rebuild to finish')
            if context.scene.get('river_candidate') == 'river-dream-v5':
                from layer_editor import pending_rocks
                if any(pending_rocks(layer) for layer in (core().NEAR,core().FAR)):
                    raise ValueError('Rebuild changed rocks before saving and exporting')
            c=core(); out=Path(context.scene.get('river_export_path',str(c.HOME/'output_v3/runtime')))
            out.mkdir(parents=True,exist_ok=True)
            command=c.export_command(out)
            if self.plate_only: command.append('--plate-only')
            self._log=open(out/'export.log','w',encoding='utf-8')
            kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            self._proc=subprocess.Popen(command,stdout=self._log,stderr=subprocess.STDOUT,**kwargs)
            self._timer=context.window_manager.event_timer_add(1,window=context.window)
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'},'Exporting a copy of the saved scene. See '+str(out/'export.log'))
            return {'RUNNING_MODAL'}
        except Exception as e:
            self.report({'ERROR'},str(e)); return {'CANCELLED'}
    def modal(self,context,event):
        if event.type!='TIMER' or self._proc.poll() is None: return {'PASS_THROUGH'}
        self._log.close(); context.window_manager.event_timer_remove(self._timer)
        self.report({'INFO'} if self._proc.returncode==0 else {'ERROR'},
                    'Export complete.' if self._proc.returncode==0 else 'Export failed; inspect export.log. Previous package retained.')
        return {'FINISHED'} if self._proc.returncode==0 else {'CANCELLED'}

class RIVER_PT_tools(bpy.types.Panel):
    bl_label='River Background'; bl_idname='RIVER_PT_tools'; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='River'
    def draw(self,context):
        l=self.layout
        box=l.box(); box.label(text='Compose with the game foreground')
        box.operator('river.preview',text='Foreground + background',icon='SCENE_DATA').mode='COMPOSE'
        row=box.row(align=True)
        row.operator('river.preview',text='Background only').mode='BACKGROUND'
        row.operator('river.preview',text='Opening camera').mode='CAMERA'
        box.label(text='Foreground is locked and excluded from export.')
        box.label(text='Game lighting and water are previewed in-game.')
        l.operator('river.generate',text='Create rock from outline / preset').mode='CREATE'
        ob=context.active_object
        if ob and 'river_recipe' in ob:
            l.label(text=ob.get('river_mode','PROCEDURAL').title()+' rock')
            l.operator('river.generate',text='Rebuild selected rock').mode='REBUILD'
            l.operator('river.generate',text='Rebuild as new variant').mode='VARIANT'
            for key,title in [('UNIQUE','Make unique'),('MANUAL','Keep manual mesh'),('OUTLINE','Edit source outline'),
                              ('SOURCES','Show source slabs'),('ASSEMBLE','Assemble edited slabs')]:
                l.operator('river.action',text=title).action=key
            row=l.row(); row.operator('river.action',text='Near band').action='NEAR'; row.operator('river.action',text='Far band').action='FAR'
        l.separator(); l.operator('river.action',text='Play camera route').action='PLAY'
        l.operator('river.export',text='Bake distant image').plate_only=True
        l.operator('river.export',text='Export saved background').plate_only=False
        l.label(text='Save the scene before exporting.',icon='INFO')

CLASSES=(RIVER_OT_generate,RIVER_OT_action,RIVER_OT_preview,RIVER_OT_export,RIVER_PT_tools)
def register():
    for cls in CLASSES:
        old=getattr(bpy.types,cls.__name__,None)
        if old:
            try: bpy.utils.unregister_class(old)
            except RuntimeError: pass
        bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
if __name__=='__main__': register()
