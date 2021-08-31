import types
from typing import Type

from zenml.pipelines.base_pipeline import BasePipeline


def SimplePipeline(func: types.FunctionType) -> Type:
    """

    Args:
      func: types.FunctionType:

    Returns:

    """
    pipeline_class = type(
        func.__name__, (BasePipeline,), {"connect": staticmethod(func)}
    )

    return pipeline_class
