#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_heap_caps.h"

// TensorFlow Lite for Microcontrollers Headers
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

static const char *TAG = "TFLM_PSRAM";

// 1. Placeholder for your 8-bit quantized model (FlatBuffer array)
// Replace with your converted .tflite model byte array
extern const unsigned char g_model[]; 
extern const int g_model_len;

// Tensor Arena Size: 2 MB (allocated in PSRAM)
constexpr int kTensorArenaSize = 2 * 1024 * 1024;

extern "C" void app_main(void) {
    ESP_LOGI(TAG, "Initializing TFLM with PSRAM...");

    // 2. Load and verify model
    const tflite::Model* model = tflite::GetModel(g_model);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        ESP_LOGE(TAG, "Model schema mismatch!");
        return;
    }

    // 3. Allocate Tensor Arena explicitly in 8MB PSRAM (SPIRAM)
    uint8_t* tensor_arena = (uint8_t*)heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (tensor_arena == nullptr) {
        ESP_LOGE(TAG, "Failed to allocate %d bytes in PSRAM!", kTensorArenaSize);
        return;
    }
    ESP_LOGI(TAG, "Successfully allocated 2MB Tensor Arena in Octal PSRAM.");

    // 4. Register Op Resolver (Add operations used by your model)
    // Using MicroMutableOpResolver saves flash by registering only needed layers
    static tflite::MicroMutableOpResolver<5> resolver;
    resolver.AddFullyConnected();
    resolver.AddConv2D();
    resolver.AddDepthwiseConv2D();
    resolver.AddReshape();
    resolver.AddSoftmax();

    // 5. Instantiate Interpreter
    static tflite::MicroInterpreter interpreter(
        model, resolver, tensor_arena, kTensorArenaSize);

    // 6. Allocate Tensors inside PSRAM Arena
    TfLiteStatus allocate_status = interpreter.AllocateTensors();
    if (allocate_status != kTfLiteOk) {
        ESP_LOGE(TAG, "AllocateTensors() failed");
        return;
    }

    // 7. Get pointers to Input and Output Tensors
    TfLiteTensor* input = interpreter.input(0);
    TfLiteTensor* output = interpreter.output(0);

    ESP_LOGI(TAG, "Input Tensor Shape: %d x %d", input->dims->data[0], input->dims->data[1]);
    (void)output;
    ESP_LOGI(TAG, "TFLM Engine Ready. Performing test inference...");

    // Example: Fill input tensor with data
    // input->data.int8[0] = 127;

    // 8. Run Inference
    TfLiteStatus invoke_status = interpreter.Invoke();
    if (invoke_status != kTfLiteOk) {
        ESP_LOGE(TAG, "Inference invocation failed");
        return;
    }

    ESP_LOGI(TAG, "Inference executed successfully!");
}
