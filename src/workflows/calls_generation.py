# Copyright 2023 Iguazio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
from typing import List

import kfp
from kfp import dsl
import mlrun

output_directory = os.path.abspath("./outputs")


@kfp.dsl.pipeline()
def pipeline(
    amount: int,
    generation_model: str,
    text_to_speech_model: str,
    language: str,
    available_voices: List[str],
    min_time: int,
    max_time: int,
    from_date: str,
    to_date: str,
    from_time: str,
    to_time: str,
    num_clients: int,
    num_agents: int,
    generate_clients_and_agents: bool = True,
    
):
    # Get the project:
    project = mlrun.get_current_project()
    
    with dsl.Condition(generate_clients_and_agents == True) as generate_data_condition:
        
        # Generate client data:
        client_data_generator_function = project.get_function("json-data-generator")
        client_data_generator_function.apply(mlrun.auto_mount())
        client_data_run = project.run_function(
            client_data_generator_function,
            handler="generate_data",
            params={
                "amount": num_clients,
                "model_name": generation_model,
                "language": language,
                "fields": ["first name", "last_name", "phone_number", "email", "client_id"],
            },
            returns=[
                "clients: file",
            ],
        )
        

        # Insert client data to database
        db_management_function = project.get_function("db-management")
        # db_management_function.apply(mlrun.auto_mount())
        project.run_function(
            db_management_function,
            handler="insert_clients",
            inputs={
                "clients": client_data_run.outputs["clients"],
            },
        )


        # Generate agent data:
        agent_data_generator_function = project.get_function("json-data-generator")
        agent_data_generator_function.apply(mlrun.auto_mount())
        agent_data_run = project.run_function(
            agent_data_generator_function,
            handler="generate_data",
            params={
                "amount": num_agents,
                "model_name": generation_model,
                "language": language,
                "fields": ["first_name", "last_name", "agent_id"],
            },
            returns=[
                "agents: file",
            ],
        )
        
        
        # Insert agent data to database
        db_management_function = project.get_function("db-management")
        # db_management_function.apply(mlrun.auto_mount())
        project.run_function(
            db_management_function,
            handler="insert_agents",
            inputs={
                "agents": agent_data_run.outputs["agents"],
            },
        )

    
    # Get agents from database
    db_management_function = project.get_function("db-management")
    # db_management_function.apply(mlrun.auto_mount())
    get_agents_run = project.run_function(
        db_management_function,
        handler="get_agents",
        returns=[
            "agents: file" 
        ],
    ).after(generate_data_condition)
    
    
    # Get clients from database
    db_management_function = project.get_function("db-management")
    # db_management_function.apply(mlrun.auto_mount())
    get_clients_run = project.run_function(
        db_management_function,
        handler="get_clients",
        returns=[
            "clients: file" 
        ],
    ).after(generate_data_condition)
    
    # Generate conversations texts:
    conversations_generator_function = project.get_function("conversations-generator")
    conversations_generator_function.apply(mlrun.auto_mount())
    generate_conversations_run = project.run_function(
        conversations_generator_function,
        handler="generate_conversations",
        params={
            "amount": amount,
            "output_directory": os.path.join(
                output_directory, "generated_conversations"
            ),
            "model_name": generation_model,
            "language": language,
            "min_time": min_time,
            "max_time": max_time,
            "from_date": from_date,
            "to_date": to_date,
            "from_time": from_time,
            "to_time": to_time,

        },
        inputs={
            "agent_data": get_agents_run.outputs['agents'],
            "client_data": get_clients_run.outputs['clients'],
        },
        returns=[
            "conversations: path",
            "metadata: dataset",
            "ground_truths: dataset",
        ],
    )

    # Text to audio:
    text_to_audio_generator_function = project.get_function("text-to-audio-generator")
    text_to_audio_generator_function.apply(mlrun.auto_mount())
    generate_multi_speakers_audio_run = project.run_function(
        text_to_audio_generator_function,
        handler="generate_multi_speakers_audio",
        inputs={"data_path": generate_conversations_run.outputs["conversations"]},
        params={
            "output_directory": os.path.join(output_directory, "audio_files"),
            "speakers": {"Agent": 0, "Client": 1},
            "available_voices": available_voices,
            "use_small_models": text_to_speech_model == "small",
        },
        returns=[
            "audio_files: path",
            "audio_files_dataframe: dataset",
            "text_to_speech_errors: file",
        ],
    )

    # Create the input batch:
    create_batch_for_analysis_run = project.run_function(
        conversations_generator_function,
        handler="create_batch_for_analysis",
        inputs={
            "conversations_data": generate_conversations_run.outputs["metadata"],
            "audio_files": generate_multi_speakers_audio_run.outputs[
                "audio_files_dataframe"
            ],
        },
        returns=["calls_batch: dataset"],
    )
