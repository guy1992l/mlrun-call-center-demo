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
import ast
import datetime
from typing import List, Optional, Tuple, Union

import mlrun
import pandas as pd
from sqlalchemy import (  # ForeignKey,
    Boolean,
    Date,
    Engine,
    Enum,
    Float,
    Integer,
    String,
    Time,
    bindparam,
    create_engine,
    insert,
    update,
    select,
)
from sqlalchemy.orm import (  # relationship,
    Mapped,
    declarative_base,
    mapped_column,
    sessionmaker,
)

from src.common import CallStatus, ProjectSecrets

ID_LENGTH = 32
FILE_PATH_LENGTH = 500

Base = declarative_base()


# TODO: client table
# class Client(Base):
#     __tablename__ = "client"
#
#     # Columns:
#     client_id: Mapped[str] = mapped_column(String(length=ID_LENGTH), primary_key=True)
#     first_name: Mapped[str] = mapped_column(String(length=30))
#     last_name: Mapped[str] = mapped_column(String(length=30))
#     phone: Mapped[str] = mapped_column(String(length=20))
#     email: Mapped[str] = mapped_column(String(length=50))
#
#     # Many-to-one relationship:
#     calls: Mapped[List["Call"]] = relationship(back_populates="client", lazy=True)


# TODO: agent table
# class Agent(Base):
#     __tablename__ = "agent"
#
#     # Columns:
#     agent_id: Mapped[str] = mapped_column(String(length=ID_LENGTH), primary_key=True)
#     first_name: Mapped[str] = mapped_column(String(length=30))
#     last_name: Mapped[str] = mapped_column(String(length=30))
#     phone: Mapped[str] = mapped_column(String(length=20))
#     email: Mapped[str] = mapped_column(String(length=50))
#
#     # Many-to-one relationship:
#     calls: Mapped[List["Call"]] = relationship(back_populates="agent", lazy=True)


class Call(Base):
    __tablename__ = "call"

    # Metadata:
    call_id: Mapped[str] = mapped_column(String(length=ID_LENGTH), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(length=ID_LENGTH),  # TODO: ForeignKey("client.id")
    )
    agent_id: Mapped[str] = mapped_column(
        String(length=ID_LENGTH),  # TODO: ForeignKey("agent.id")
    )
    date: Mapped[datetime.date] = mapped_column(Date())
    time: Mapped[datetime.time] = mapped_column(Time())
    duration: Mapped[int] = mapped_column(Integer())
    status: Mapped[CallStatus] = mapped_column(Enum(CallStatus))
    # Files:
    audio_file: Mapped[str] = mapped_column(String(length=FILE_PATH_LENGTH))
    # TODO: processed_audio_file: Mapped[Optional[str]] = mapped_column(String(length=FILE_PATH_LENGTH))
    transcription_file: Mapped[Optional[str]] = mapped_column(
        String(length=FILE_PATH_LENGTH)
    )
    translation_file: Mapped[Optional[str]] = mapped_column(
        String(length=FILE_PATH_LENGTH)
    )
    anonymized_file: Mapped[Optional[str]] = mapped_column(
        String(length=FILE_PATH_LENGTH)
    )
    # Transcription:
    language: Mapped[Optional[str]] = mapped_column(String(length=3))
    language_probability: Mapped[Optional[float]] = mapped_column(Float())
    # Analysis:
    topic: Mapped[Optional[str]] = mapped_column(String(length=50))
    summary: Mapped[Optional[str]] = mapped_column(String(length=1000))
    concern_addressed: Mapped[Optional[bool]] = mapped_column(Boolean())
    client_tone: Mapped[Optional[str]] = mapped_column(String(length=20))
    agent_tone: Mapped[Optional[str]] = mapped_column(String(length=20))

    # TODO: One-to-many relationships:
    # client: Mapped["Client"] = relationship(back_populates="calls", lazy=True)
    # agent: Mapped["Agent"] = relationship(back_populates="calls", lazy=True)


def create_tables(project: mlrun.projects.MlrunProject):
    """
    Create the call center schema tables for when creating or loading the MLRun project.

    :param project: The MLRun project with the MySQL secrets.
    """
    # Create an engine:
    engine = _get_engine(context_or_project=project)

    # Create the schema's tables:
    Base.metadata.create_all(engine)


def insert_calls(
    context: mlrun.MLClientCtx, calls: pd.DataFrame
) -> Tuple[pd.DataFrame, List[str]]:
    # Create an engine:
    engine = _get_engine(context_or_project=context)

    # Initialize a session maker:
    session = sessionmaker(engine)

    # Cast data from dataframe to a list of dictionaries:
    records = calls.to_dict(orient="records")

    # Insert the new calls into the table and commit:
    with session.begin() as sess:
        sess.execute(insert(Call), records)

    # Return the metadata and audio files:
    audio_files = list(calls["audio_file"])
    return calls, audio_files


def update_calls(
    context: mlrun.MLClientCtx,
    status: str,
    table_key: str,
    data_key: str,
    data: pd.DataFrame,
):
    """

    :param context:
    :param status:
    :param table_key:
    :param data_key:
    :param data:
    """
    # Create an engine:
    engine = _get_engine(context_or_project=context)

    # Initialize a session maker:
    session = sessionmaker(engine)

    # Add the status to the dataframe:
    data["status"] = [CallStatus(status)] * len(data)

    # Cast data from dataframe to a list of dictionaries:
    data = data.to_dict(orient="records")

    # Insert the new calls into the table and commit:
    with session.begin() as sess:
        sess.connection().execute(
            update(Call).where(getattr(Call, table_key) == bindparam(data_key)), data
        )


def get_calls(project: mlrun.projects.MlrunProject) -> pd.DataFrame:
    # Create an engine:
    engine = _get_engine(context_or_project=project)

    # Initialize a session maker:
    session = sessionmaker(engine)

    # Select all calls:
    with session.begin() as sess:
        calls = pd.read_sql(select(Call), sess.connection())

    return calls


def _get_engine(
    context_or_project: Union[mlrun.MLClientCtx, mlrun.projects.MlrunProject]
) -> Engine:
    # Get the url and connection arguments:
    url = context_or_project.get_secret(key=ProjectSecrets.MYSQL_URL)

    # Create an engine:
    return create_engine(url=url)
