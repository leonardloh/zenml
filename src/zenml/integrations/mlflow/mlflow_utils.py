#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
import os
from pathlib import Path
from typing import Optional

from mlflow import (  # type: ignore
    ActiveRun,
    get_experiment_by_name,
    search_runs,
    set_experiment,
    set_tracking_uri,
    start_run,
)

from zenml.integrations.registry import integration_registry
from zenml.logger import get_logger
from zenml.repository import Repository

logger = get_logger(__name__)


def local_mlflow_backend(root: Optional[Path] = None) -> str:
    """Returns the local mlflow backend inside the global zenml directory

    Args:
        root: Optional root directory of the repository. If no path is
            given, this function tries to find the repository using the
            environment variable `ZENML_REPOSITORY_PATH` (if set) and
            recursively searching in the parent directories of the current
            working directory.

    Returns:
        The MLflow tracking URI for the local mlflow backend.
    """
    repo = Repository(root)
    integration_registry.activate_integrations()
    artifact_store = repo.active_stack.artifact_store
    local_mlflow_backend_uri = os.path.join(artifact_store.path, "mlruns")
    if not os.path.exists(local_mlflow_backend_uri):
        os.makedirs(local_mlflow_backend_uri)
        # TODO [medium]: safely access (possibly non-existent) artifact stores
    return "file:" + local_mlflow_backend_uri


def setup_mlflow(
    backend_store_uri: Optional[str] = None, experiment_name: str = "default"
) -> None:
    """Setup all mlflow related configurations. This includes specifying which
    mlflow tracking uri should be used and which experiment the tracking
    will be associated with.

    Args:
        backend_store_uri: The mlflow backend to log to
        experiment_name: The experiment name under which all runs will be
            tracked. If no MLflow experiment with this name exists, onw will be
            created.

    """
    # TODO [ENG-316]: Implement a way to get the mlflow token and set
    #  it as env variable at MLFLOW_TRACKING_TOKEN
    if not backend_store_uri:
        backend_store_uri = local_mlflow_backend()
    logger.debug("Setting the MLflow tracking uri to %s", backend_store_uri)
    set_tracking_uri(backend_store_uri)
    # Set which experiment is used within mlflow
    logger.debug("Setting the MLflow experiment name to %s", experiment_name)
    set_experiment(experiment_name)


def get_or_create_mlflow_run(experiment_name: str, run_name: str) -> ActiveRun:
    """Get or create an MLflow ActiveRun object for the given experiment and
    run name.

    IMPORTANT: this function is not race condition proof. If two or more
    processes call it at the same time and with the same arguments, it could
    lead to a situation where two or more MLflow runs with the same name
    and different IDs are created.

    Args:
        experiment_name (str): the experiment name for the run. The experiment
            must already be created in MLflow (e.g. by calling `setup_mlflow`
            beforehand)
        run_name (str): the name of the MLflow run. If a run with this name
            does not exist, one will be created, otherwise the existing run
            will be reused

    Returns:
        ActiveRun: an active MLflow run object with the specified name
    """
    mlflow_experiment = get_experiment_by_name(experiment_name)

    # TODO [medium]: find a solution to avoid race-conditions while logging
    #   to MLflow from parallel steps
    runs = search_runs(
        experiment_ids=[mlflow_experiment.experiment_id],
        filter_string=f'tags.mlflow.runName = "{run_name}"',
        output_format="list",
    )
    if runs:
        run_id = runs[0].info.run_id
        return start_run(
            run_id=run_id, experiment_id=mlflow_experiment.experiment_id
        )
    return start_run(
        run_name=run_name, experiment_id=mlflow_experiment.experiment_id
    )
