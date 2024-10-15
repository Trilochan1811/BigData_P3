import grpc
from concurrent import futures
import time
import table_pb2_grpc
import table_pb2
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import os
import threading
import logging

logging.basicConfig(level=logging.INFO)

class TableServicer(table_pb2_grpc.TableServicer):
    def __init__(self):
        self.file_paths = {"csv": [], "parquet": []}
        self.lock = threading.Lock()

    def Upload(self, request, context):
        csv_data = request.csv_data

        try:
            # Generate filenames outside the lock
            with self.lock:
                csv_index = len(self.file_paths['csv'])
                parquet_index = len(self.file_paths['parquet'])

            csv_filename = f"uploaded_data_{csv_index}.csv"
            parquet_filename = f"uploaded_data_{parquet_index}.parquet"

            # File I/O operations outside the lock
            with open(csv_filename, "wb") as f:
                f.write(csv_data)

            df = pd.read_csv(csv_filename)
            table = pa.Table.from_pandas(df)
            pq.write_table(table, parquet_filename)

            # Update shared data structure with lock
            with self.lock:
                self.file_paths["csv"].append(os.path.abspath(csv_filename))
                self.file_paths["parquet"].append(os.path.abspath(parquet_filename))

            logging.info(f"Received CSV data for upload. Files saved as {csv_filename} and {parquet_filename}.")
            return table_pb2.UploadResp(error="")
        except Exception as e:
            logging.error(f"Error in Upload: {str(e)}")
            return table_pb2.UploadResp(error=str(e))

    def ColSum(self, request, context):
        column = request.column
        format_type = request.format
        total_sum = 0

        try:
            # Get a copy of file paths under lock
            with self.lock:
                files_to_process = self.file_paths[format_type].copy()

            for file_path in files_to_process:
                if format_type == "csv":
                    try:
                        # Read CSV in chunks to handle large files
                        for chunk in pd.read_csv(file_path, usecols=[column], chunksize=10000):
                            total_sum += chunk[column].sum()
                    except ValueError:
                        # Column not found in this CSV, skip it
                        logging.warning(f"Column '{column}' not found in {file_path}")
                        continue
                elif format_type == "parquet":
                    try:
                        # Read only the required column from Parquet file
                        table = pq.read_table(file_path, columns=[column])
                        column_array = table[column].combine_chunks()
                        total_sum += column_array.sum().as_py()
                    except (KeyError, pa.lib.ArrowInvalid):
                        # Column not found in this Parquet file, skip it
                        logging.warning(f"Column '{column}' not found in {file_path}")
                        continue

            return table_pb2.ColSumResp(error="", total=int(total_sum))
        except Exception as e:
            logging.error(f"Error in ColSum: {str(e)}")
            return table_pb2.ColSumResp(error=str(e), total=0)

def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        options=[("grpc.so_reuseport", 0)]
    )
    table_pb2_grpc.add_TableServicer_to_server(TableServicer(), server)
    server.add_insecure_port('[::]:5440')
    server.start()
    logging.info("Server started on port 5440...")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
