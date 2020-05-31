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
        logger = sgtk.platform.get_logger("tk-multi-workfile2")
        sg = engine.shotgun
        name = os.path.basename(cmds.file(q=True, sn=True))
        task = context.task
        entity = context.entity

        # Consulado framework init
        tk_consuladoutils = self.load_framework("tk-framework-consuladoutils_v0.x.x")
        consulado_globals = tk_consuladoutils.import_module("shotgun_globals")
        maya_utils = tk_consuladoutils.import_module("maya_utils")
        consulado_model = tk_consuladoutils.import_module("shotgun_model")

        logger.debug("Starting to read a scene data")
        sg_node_name = consulado_globals.get_custom_entity_by_alias("node")
        sg_node_type_name = consulado_globals.get_custom_entity_by_alias("node_type")
        node_fields = [
            "project",
            "id",
            "code",
            "sg_link",
            "sg_type",
            "sg_downstream_node",
            "sg_upstream_node",
            "published_file",
        ]
        ms = maya_utils.MayaScene()
        for asset in ms:
            logger.debug("asset: %s" % asset)
            if not asset.is_reference:
                logger.debug("This asset isn't referenced")
                # ensures that all geometries has the consuladoNodeID
                asset.create_sg_attr()

            Nodes = consulado_model.EntityIter(sg_node_name, node_fields, context, sg)
            for geo in asset:
                logger.debug("starting to check the geo %s" % geo)
                if not hasattr(geo, ms.DEFAULT_CONSULADO_GEO_ATTR):
                    logger.debug(
                        "This geometry haven't the attribute %s"
                        % ms.DEFAULT_CONSULADO_GEO_ATTR
                    )
                    continue

                node = Nodes.add_new_entity()
                node.code = geo.fullPath()
                node.sg_link = entity
                # TODO: Remover hardcode
                node.sg_type = {
                    "type": sg_node_type_name,
                    "id": 1,
                }
                node.load()
                logger.debug("Found node %s" % node.shotgun_entity_data)
                if node.id is None:
                    node.create()
                else:
                    node.update()
                try:
                    attr = getattr(geo, ms.DEFAULT_CONSULADO_GEO_ATTR)
                    attr.set(node.id)
                except Exception as e:
                    logger.error(
                        "Error while set the attribute %s on geo %s, because %s"
                        % (ms.DEFAULT_CONSULADO_GEO_ATTR, geo, e)
                    )

        # TODO: Caso seja uma task do tipo anim ou shot, verificar as cameras e os namespaces atuais
        # TODO: Verificar se a cena atual eh um workspace conhecido e caso nao seja, adiciona-lo no shotgun
        # TODO: Caso a cena possua alguma geometria nao referenciada, criar ids e adicionar ao workspace atual
