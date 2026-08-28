cmake_minimum_required(VERSION 3.16)
project(audio_pipeline_consumer C)

find_package(AudioPipeline CONFIG REQUIRED)

add_executable(audio_pipeline_consumer consumer.c)
target_link_libraries(audio_pipeline_consumer PRIVATE AudioPipeline::core)
