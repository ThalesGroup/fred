# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.structure import Configuration

logger = logging.getLogger(__name__)

# Create the SQLAlchemy engine.
engine = None

# Create a configured "Session" class.
SessionLocal = None

def initialize_feedback_db(config: Configuration):
    """
    Initialize the Keycloak authentication settings from the given configuration.
    """
    global engine
    global SessionLocal
    logger.debug(config)
    if config.feedback.type == "postgres":
        db_type = "postgresql"
    db_host = config.feedback.db_host
    db_port = config.feedback.db_port
    db_name = config.feedback.db_name
    user = config.feedback.user
    password = config.feedback.password
    try:
        engine = create_engine(f"{db_type}://{user}:{password}@{db_host}:{db_port}/{db_name}")
        logger.info(f"SQL Engine created successfully.")
    except Exception as e:
        logger.error("SQL Engine creation failed: %s.", e)
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info(f"SQL Session created successfully.")
    except Exception as e:
        logger.error("SQL Session creation failed: %s.", e)

def get_engine():
    """Get Engine after initialization."""
    if engine is None:
        raise RuntimeError("Engine is not initialized yet.")
    return engine

def get_db():
    """
    Dependency function that creates a new database session for a request,
    then closes it after the request is completed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
