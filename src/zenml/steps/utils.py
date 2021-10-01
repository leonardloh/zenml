#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.

"""
The collection of utility functions/classes are inspired by their original
implementation of the Tensorflow Extended team, which can be found here:

https://github.com/tensorflow/tfx/blob/master/tfx/dsl/component/experimental/decorators.py

This version is heavily adjusted to work with the Pipeline-Step paradigm which
is proposed by ZenML.
"""

from __future__ import absolute_import, division, print_function

import json
from typing import Type
import inspect
import sys
from typing import Any, Callable, Dict, List, Text

import pydantic
from pydantic import create_model
from tfx import types as tfx_types
from tfx.dsl.component.experimental.decorators import _SimpleComponent
from tfx.dsl.components.base.base_executor import BaseExecutor
from tfx.dsl.components.base.executor_spec import ExecutorClassSpec
from tfx.types import component_spec

from zenml.annotations import Input, Output
from zenml.artifacts.base_artifact import BaseArtifact
from zenml.utils.exceptions import StepInterfaceError


class _FunctionExecutor(BaseExecutor):
    """ """

    _FUNCTION = staticmethod(lambda: None)

    def Do(
            self,
            input_dict: Dict[Text, List[tfx_types.Artifact]],
            output_dict: Dict[Text, List[tfx_types.Artifact]],
            exec_properties: Dict[Text, Any],
    ):
        function_args = {}
        for name, artifact in input_dict.items():
            if len(artifact) == 1:
                function_args[name] = artifact[0]
            else:
                raise ValueError(
                    (
                        "Expected input %r to %s to be a singleton "
                        "ValueArtifact channel (got %s instead)."
                    )
                    % (name, self, artifact)
                )

        return_artifact = output_dict.pop("return_output", None)
        for name, artifact in output_dict.items():
            if len(artifact) == 1:
                function_args[name] = artifact[0]
            else:
                raise ValueError(
                    (
                        "Expected output %r to %s to be a singleton "
                        "ValueArtifact channel (got %s instead)."
                    )
                    % (name, self, artifact)
                )

        ####
        spec = inspect.getfullargspec(self._FUNCTION)

        args = spec.args

        inputs_to_take_care_of = []
        param_spec = {}
        for arg in args:
            arg_type = spec.annotations.get(arg, None)
            if isinstance(arg_type, Input):
                if not issubclass(arg_type.type, BaseArtifact):
                    inputs_to_take_care_of.append(arg)
            elif isinstance(arg_type, Output):
                pass
            else:
                param_spec.update({arg: arg_type})

        new_exec = {k: json.loads(v) for k,v in exec_properties.items()}
        pydantic_c: Type[pydantic.BaseModel] = create_model(
            "params", **{k: (v, ...) for k, v in param_spec.items()}
        )
        function_args.update(pydantic_c.parse_obj(new_exec).dict())

        returns = self._FUNCTION(**function_args)

        if return_artifact is not None:
            if returns is not None:
                return_artifact.materializers.json.write(returns)
            else:
                raise StepInterfaceError()

        if returns is not None and return_artifact is None:
            raise StepInterfaceError()


def generate_component(step) -> Callable[..., Any]:
    spec_inputs, spec_outputs, spec_params = {}, {}, {}
    for key, artifact_type in step.INPUT_SPEC.items():
        spec_inputs[key] = component_spec.ChannelParameter(type=artifact_type)
    for key, artifact_type in step.OUTPUT_SPEC.items():
        spec_outputs[key] = component_spec.ChannelParameter(type=artifact_type)
    for key, prim_type in step.PARAM_SPEC.items():
        spec_params[key] = component_spec.ExecutionParameter(type=str)

    component_spec_class = type(
        "%s_Spec" % step.__class__.__name__,
        (tfx_types.ComponentSpec,),
        {
            "INPUTS": spec_inputs,
            "OUTPUTS": spec_outputs,
            "PARAMETERS": spec_params,
        },
    )

    executor_class = type(
        "%s_Executor" % step.__class__.__name__,
        (_FunctionExecutor,),
        {
            "_FUNCTION": staticmethod(step.process),
            "__module__": step.__module__,
        },
    )

    module = sys.modules[step.__module__]
    setattr(module, "%s_Executor" % step.__class__.__name__, executor_class)

    executor_spec_instance = ExecutorClassSpec(executor_class=executor_class)

    return type(
        step.__class__.__name__,
        (_SimpleComponent,),
        {
            "SPEC_CLASS": component_spec_class,
            "EXECUTOR_SPEC": executor_spec_instance,
            "__module__": step.__module__,
        },
    )