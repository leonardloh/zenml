#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
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
import shutil
from typing import Generator
from unittest.mock import PropertyMock

import pytest
from pytest_mock import MockerFixture

from zenml.repository import Repository
from zenml.stack import Stack

AWS_REGION = "us-east-1"
AWS_EKS_CLUSTER = "zenhacks-cluster"
ECR_REGISTRY_NAME = "715803424590.dkr.ecr.us-east-1.amazonaws.com"
S3_BUCKET_NAME = "s3://zenbytes-bucket"
KUBEFLOW_NAMESPACE = "kubeflow"
KUBE_CONTEXT = "zenml-eks"

@pytest.fixture(scope="module")
def shared_kubeflow_profile(
    base_profile: Repository,
    module_mocker: MockerFixture,
) -> Generator[Repository, None, None]:
    """Creates and activates a locally provisioned kubeflow stack.

    As the resource provisioning for the local kubeflow deployment takes quite
    a while, this fixture has a module scope and will therefore only run once.

    **Note**: The fixture should not be used directly. Use the
    `clean_kubeflow_repo` fixture instead that builds on top of this and
    provides the test with a clean working directory and artifact/metadata
    store.

    Args:
        base_profile: The base ZenML repository for tests with a clean profile.
        module_mocker: Mocker fixture

    Yields:
        The input repository with a local kubeflow stack provisioned for the
        module active profile.
    """
    from zenml.integrations.kubeflow.orchestrators import KubeflowOrchestrator
    from zenml.container_registries import DefaultContainerRegistry
    from zenml.integrations.kubeflow.metadata_stores import \
        KubeflowMetadataStore
    from zenml.integrations.s3.artifact_stores import S3ArtifactStore

    # Patch the ui daemon as forking doesn't work well with pytest
    module_mocker.patch.object(KubeflowMetadataStore,
                               "resume")
    module_mocker.patch("zenml.integrations.kubeflow.metadata_stores"
                        ".kubeflow_metadata_store.KubeflowMetadataStore"
                        ".is_running",
                        new_callable=PropertyMock(return_value=True))

    # Register and activate the kubeflow stack
    orchestrator = KubeflowOrchestrator(
        name="eks_orchestrator",
        custom_docker_base_image_name="custom-base-image:latest",
        synchronous=True,
        kubernetes_context=KUBE_CONTEXT,
        skip_ui_daemon_provisioning=True
    )

    metadata_store = KubeflowMetadataStore(
        name="kubeflow_metadata_store",
    )
    artifact_store = S3ArtifactStore(
        name="s3_store",
        path=S3_BUCKET_NAME
    )
    container_registry = DefaultContainerRegistry(
        name="ecr_registry", uri=ECR_REGISTRY_NAME
    )
    kubeflow_stack = Stack(
        name="aws_kubeflow_stack",
        orchestrator=orchestrator,
        metadata_store=metadata_store,
        artifact_store=artifact_store,
        container_registry=container_registry,
    )
    # breakpoint()
    base_profile.register_stack(kubeflow_stack)
    base_profile.activate_stack(kubeflow_stack.name)

    # Provision resources for the kubeflow stack
    kubeflow_stack.provision()
    kubeflow_stack.resume()

    yield base_profile

    # Deprovision the resources after all tests in this module are finished
    kubeflow_stack.deprovision()


def cleanup_active_profile() -> None:
    """Clean up all previously stored information from the artifact store and
    metadata store in the current stack.
    """

    kubeflow_stack = Repository().active_stack

    # Delete the artifact store and metadata store of previous tests
    if os.path.exists(kubeflow_stack.artifact_store.path):
        shutil.rmtree(kubeflow_stack.artifact_store.path)


@pytest.fixture
def clean_kubeflow_profile(
    shared_kubeflow_profile: Repository,
) -> Generator[Repository, None, None]:
    """Creates a clean environment with a provisioned local kubeflow stack.

    This fixture reuses the stack configuration from the shared kubeflow
    profile. The stack resources are already provisioned by the module-scoped
    fixture and all that's done here is to clean up all previously stored
    information from the artifact store and metadata store.

    Args:
        shared_kubeflow_profile: A repository with a provisioned local kubeflow
            stack

    Yields:
        An empty repository with a provisioned local kubeflow stack.
    """
    # cleanup_active_profile()

    yield shared_kubeflow_profile


@pytest.fixture
def clean_base_profile(
    base_profile: Repository,
) -> Generator[Repository, None, None]:
    """Creates a clean environment with an empty artifact store and metadata
    store out of the shared base profile.

    Args:
        base_profile: A repository with a provisioned profile shared by all
            tests in the current module.

    Yields:
        A repository with an empty artifact store and metadata store.
    """
    cleanup_active_profile()

    yield base_profile
