# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import maya.cmds as cmds
import os
import sgtk
from sgtk.platform.qt import QtGui

HookClass = sgtk.get_hook_baseclass()


class SceneOperation(HookClass):
    """
    Hook called to perform an operation with the
    current scene
    """

    def __init__(self, *args, **kwargs):
        super(SceneOperation, self).__init__(*args, **kwargs)

        self.logger = sgtk.platform.get_logger("tk-multi-workfile2")

        # Consulado framework init
        self.tk_consuladoutils = self.load_framework(
            "tk-framework-consuladoutils_v0.x.x"
        )
        self.consulado_globals = tk_consuladoutils.import_module("shotgun_globals")
        self.maya_utils = tk_consuladoutils.import_module("maya_utils")
        self.consulado_model = tk_consuladoutils.import_module("shotgun_model")

        self.sg_node_name = consulado_globals.get_custom_entity_by_alias("node")
        self.sg_node_type_name = consulado_globals.get_custom_entity_by_alias(
            "node_type"
        )

    def execute(
        self,
        operation,
        file_path,
        context,
        parent_action,
        file_version,
        read_only,
        **kwargs
    ):
        """
        Main hook entry point

        :param operation:       String
                                Scene operation to perform

        :param file_path:       String
                                File path to use if the operation
                                requires it (e.g. open)

        :param context:         Context
                                The context the file operation is being
                                performed in.

        :param parent_action:   This is the action that this scene operation is
                                being executed for.  This can be one of:
                                - open_file
                                - new_file
                                - save_file_as
                                - version_up

        :param file_version:    The version/revision of the file to be opened.  If this is 'None'
                                then the latest version should be opened.

        :param read_only:       Specifies if the file should be opened read-only or not

        :returns:               Depends on operation:
                                'current_path' - Return the current scene
                                                 file path as a String
                                'reset'        - True if scene was reset to an empty
                                                 state, otherwise False
                                all others     - None
        """

        if operation == "current_path":
            # return the current scene path
            return cmds.file(query=True, sceneName=True)
        elif operation == "open":
            # do new scene as Maya doesn't like opening
            # the scene it currently has open!
            cmds.file(new=True, force=True)
            cmds.file(file_path, open=True, force=True)
        elif operation == "save":
            self.update_scene_info()
            # save the current scene:
            cmds.file(save=True)
        elif operation == "save_as":
            self.update_scene_info()
            # first rename the scene as file_path:
            cmds.file(rename=file_path)

            # Maya can choose the wrong file type so
            # we should set it here explicitely based
            # on the extension
            maya_file_type = None
            if file_path.lower().endswith(".ma"):
                maya_file_type = "mayaAscii"
            elif file_path.lower().endswith(".mb"):
                maya_file_type = "mayaBinary"

            # save the scene:
            if maya_file_type:
                cmds.file(save=True, force=True, type=maya_file_type)
            else:
                cmds.file(save=True, force=True)

        elif operation == "reset":
            """
            Reset the scene to an empty state
            """
            while cmds.file(query=True, modified=True):
                # changes have been made to the scene
                res = QtGui.QMessageBox.question(
                    None,
                    "Save your scene?",
                    "Your scene has unsaved changes. Save before proceeding?",
                    QtGui.QMessageBox.Yes
                    | QtGui.QMessageBox.No
                    | QtGui.QMessageBox.Cancel,
                )

                if res == QtGui.QMessageBox.Cancel:
                    return False
                elif res == QtGui.QMessageBox.No:
                    break
                else:
                    scene_name = cmds.file(query=True, sn=True)
                    if not scene_name:
                        cmds.SaveSceneAs()
                    else:
                        cmds.file(save=True)

            # do new file:
            cmds.file(newFile=True, force=True)
            return True

    def update_scene_info(self, context):
        engine = sgtk.platform.current_engine()
        sg = engine.shotgun
        name = os.path.basename(cmds.file(q=True, sn=True))
        task = context.task
        entity = context.entity

        self.logger.debug("Starting to read a scene data")
        node_fields = [
            "project",
            "id",
            "code",
            "sg_link",
            "sg_node_type",
            "sg_downstream_node",
            "sg_upstream_node",
            "published_file",
        ]
        ms = maya_utils.MayaScene()
        for asset in ms:
            self.logger.debug("asset: %s" % asset)
            if not asset.is_reference:
                self.logger.debug("This asset isn't referenced")
                # ensures that all geometries has the consuladoNodeID
                asset.create_sg_attr()

            Nodes = self.consulado_model.EntityIter(
                self.sg_node_name, node_fields, context, sg
            )
            if entity.get("type", "").lower() == "asset":
                self.logger.debug("Asset detected: %s" % entity)
                self.check_asset_nodes(Nodes, ms, entity, asset)
            else:
                self.logger.debug("Shot detected: %s" % entity)

        # TODO: Caso seja uma task do tipo anim ou shot, verificar as cameras e os namespaces atuais
        # TODO: Verificar se a cena atual eh um workspace conhecido e caso nao seja, adiciona-lo no shotgun
        # TODO: Caso a cena possua alguma geometria nao referenciada, criar ids e adicionar ao workspace atual

    def check_asset_nodes(self, node_entity, ms, entity, asset):
        for geo in asset:
            self.logger.debug("starting to check the geo %s" % geo)
            if not hasattr(geo, ms.DEFAULT_CONSULADO_GEO_ATTR):
                self.logger.debug(
                    "This geometry haven't the attribute %s"
                    % ms.DEFAULT_CONSULADO_GEO_ATTR
                )
                continue

            node = node_entity.add_new_entity()
            node.code = geo.fullPath()
            node.sg_link = entity
            # TODO: Remover hardcode
            node.sg_node_type = {
                "type": sg_node_type_name,
                "id": 1,
            }
            node.entity_filter = [
                ["code", "is", node.code],
                ["sg_link", "is", node.sg_link],
                ["sg_node_type", "is", node.sg_node_type],
            ]
            node.load()
            self.logger.debug(
                "Found the Shotguns entity node: %s" % node.shotgun_entity_data
            )
            if node.id is None:
                node.create()
            else:
                node.update()
            try:
                attr = getattr(geo, ms.DEFAULT_CONSULADO_GEO_ATTR)
                attr.set(node.id)
            except Exception as e:
                self.logger.error(
                    "Error while set the attribute %s on geo %s, because %s"
                    % (ms.DEFAULT_CONSULADO_GEO_ATTR, geo, e)
                )

    def check_cameras(self, context, maya_scene, workfile):
        # TODO: verificar as cameras
        engine = sgtk.platform.current_engine()

        sg = engine.shotgun
        name = os.path.basename(cmds.file(q=True, sn=True))
        task = context.task
        entity = context.entity

        tk_consuladoutils = self.load_framework("tk-framework-consuladoutils_v0.x.x")
        consulado_model = tk_consuladoutils.import_module("shotgun_model")

        camera_fields = [
            "project",
            "id",
            "code",
            "custom_entity04_sg_camera_custom_entity04s",
        ]
        Cameras = consulado_model.EntityIter("Camera", camera_fields, context, sg)

        for cam in maya_scene.non_default_cameras():
            self.logger.debug("Checking the camera %s" % cam.nodeName())
            sg_cam = Cameras.add_new_entity()
            sg_cam.code = cam.nodeName()
            sg_cam.custom_entity04_sg_camera_custom_entity04s = workfile
            sg_cam.entity_filter = [
                ["code", "is", sg_cam.code],
                ["custom_entity04_sg_camera_custom_entity04s", "is", workfile],
            ]
            sg_cam.load()
            if sg_cam.id is None:
                sg_cam.create()
            else:
                sg_cam.update()

    def check_namespaces(self, context, maya_scene, workfile):
        engine = sgtk.platform.current_engine()

        sg = engine.shotgun
        name = os.path.basename(cmds.file(q=True, sn=True))
        task = context.task
        entity = context.entity

        tk_consuladoutils = self.load_framework("tk-framework-consuladoutils_v0.x.x")
        consulado_model = tk_consuladoutils.import_module("shotgun_model")
        consulado_globals = tk_consuladoutils.import_module("shotgun_globals")
        sg_namespace_type = consulado_globals.get_custom_entity_by_alias("namespace")

        namespace_fields = ["project", "id", "code", "sg_link", "sg_scene"]
        sg_namespaces = consulado_model.EntityIter(
            sg_namespace_type, namespace_fields, context, sg
        )

        for namespace in maya_scene.scene_namespaces():
            self.logger.debug("checking the asset namespace: %s" % namespace)

            sg_namespace = sg_namespace.add_new_entity()
            sg_namespace.code = namespace

    def check_workfile(self, context):
        pass
