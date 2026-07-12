
# RUN ONCE TO CREATE THE VECTOR TABLE

from vectordb import init_vector_store_table
from checkpointer import init_checkpoint_tables

if __name__ == "__main__":
    init_vector_store_table()
    init_checkpoint_tables()
    print("Done — tables created.")