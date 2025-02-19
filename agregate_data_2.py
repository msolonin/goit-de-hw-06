
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import StructType, StructField, StringType, FloatType, TimestampType, IntegerType
from configs import kafka_config, SENSORS_TOPIC_NAME


os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-streaming-kafka-0-10_2.12:3.5.1,org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 pyspark-shell'



spark = (SparkSession.builder
         .appName("KafkaStreaming")
         .master("local[*]")
         .config("spark.sql.debug.maxToStringFields", "200")
         .config("spark.sql.columnNameLengthThreshold", "200")
         .getOrCreate())

alerts_df = spark.read.csv("alerts_conditions.csv", header=True)
print(alerts_df.show())

window_duration = "1 minute"
sliding_interval = "30 seconds"

df = spark \
    .readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", kafka_config['bootstrap_servers'][0]) \
    .option("kafka.security.protocol", "SASL_PLAINTEXT") \
    .option("kafka.sasl.mechanism", "PLAIN") \
    .option("kafka.sasl.jaas.config",
            'org.apache.kafka.common.security.plain.PlainLoginModule required username="admin" password="VawEzo1ikLtrA8Ug8THa";') \
    .option("subscribe", SENSORS_TOPIC_NAME) \
    .option("startingOffsets", "earliest") \
    .option("maxOffsetsPerTrigger", "300") \
    .load()

json_schema = StructType([
    StructField("sensor_id", IntegerType(), True),
    StructField("timestamp", StringType(), True),
    StructField("temperature", IntegerType(), True),
    StructField("humidity", IntegerType(), True)
])

avg_stats = df.selectExpr("CAST(key AS STRING) AS key_deserialized", "CAST(value AS STRING) AS value_deserialized", "*") \
    .drop('key', 'value') \
    .withColumnRenamed("key_deserialized", "key") \
    .withColumn("value_json", from_json(col("value_deserialized"), json_schema)) \
    .withColumn("timestamp", from_unixtime(col("value_json.timestamp").cast(DoubleType())).cast("timestamp")) \
    .withWatermark("timestamp", "10 seconds") \
    .groupBy(window(col("timestamp"), window_duration, sliding_interval)) \
    .agg(
    avg("value_json.temperature").alias("t_avg"),
    avg("value_json.humidity").alias("h_avg")
) \
    .drop("topic")

all_alerts = avg_stats.crossJoin(alerts_df)
