package com.napominator.ui.record

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.TextFields
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.napominator.nlp.NlpParser

/**
 * Экран записи голоса.
 * Режим "удержание": нажал → запись → отпустил → распознавание.
 */
@Composable
fun RecordScreen(
    onRecognized: (NlpParser.ParsedTask) -> Unit,
    onClose: () -> Unit,
    viewModel: RecordViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val amplitude by viewModel.amplitude.collectAsStateWithLifecycle()

    var showTextInput by remember { mutableStateOf(false) }
    var textInputValue by remember { mutableStateOf("") }

    // Когда распознали — передаём вверх
    LaunchedEffect(uiState) {
        if (uiState is RecordUiState.Recognized) {
            onRecognized((uiState as RecordUiState.Recognized).parsed)
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surface)
    ) {
        // Кнопка закрытия
        IconButton(
            onClick = {
                viewModel.cancelRecording()
                onClose()
            },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(8.dp)
        ) {
            Icon(Icons.Default.Close, contentDescription = "Закрыть")
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            when (val state = uiState) {
                is RecordUiState.Idle -> {
                    if (showTextInput) {
                        TextInputMode(
                            value = textInputValue,
                            onValueChange = { textInputValue = it },
                            onSave = {
                                showTextInput = false
                                viewModel.saveTextInput(textInputValue)
                            },
                            onCancel = {
                                showTextInput = false
                                textInputValue = ""
                            }
                        )
                    } else {
                        IdleContent(
                            amplitude = amplitude,
                            onStartRecording = { viewModel.startRecording() },
                            onStopRecording = { viewModel.stopRecording() },
                            onTextInput = { showTextInput = true }
                        )
                    }
                }

                is RecordUiState.Recording -> {
                    RecordingContent(
                        seconds = state.seconds,
                        amplitude = amplitude,
                        onStopRecording = { viewModel.stopRecording() }
                    )
                }

                is RecordUiState.Processing -> {
                    ProcessingContent()
                }

                is RecordUiState.Error -> {
                    ErrorContent(
                        message = state.message,
                        onRetry = { viewModel.resetToIdle() },
                        onTextInput = {
                            viewModel.resetToIdle()
                            showTextInput = true
                        }
                    )
                }

                is RecordUiState.Recognized -> {
                    // Обрабатывается в LaunchedEffect выше
                    ProcessingContent()
                }
            }
        }
    }
}

@Composable
private fun IdleContent(
    amplitude: Float,
    onStartRecording: () -> Unit,
    onStopRecording: () -> Unit,
    onTextInput: () -> Unit
) {
    // Подсказки для пользователя
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer
        )
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(
                "Примеры фраз:",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer
            )
            Spacer(Modifier.height(8.dp))
            listOf(
                "«Позвонить врачу завтра в 15:00»",
                "«Купить молоко по дороге домой»",
                "«Зарядка каждый день утром»"
            ).forEach { example ->
                Text(
                    text = example,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(vertical = 2.dp)
                )
            }
        }
    }

    Spacer(Modifier.height(48.dp))

    Text(
        text = "Удерживайте кнопку и говорите",
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center
    )

    Spacer(Modifier.height(32.dp))

    MicButton(
        isRecording = false,
        amplitude = amplitude,
        onStartRecording = onStartRecording,
        onStopRecording = onStopRecording
    )

    Spacer(Modifier.height(32.dp))

    TextButton(onClick = onTextInput) {
        Icon(Icons.Default.TextFields, contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text("Ввести текстом")
    }
}

@Composable
private fun RecordingContent(
    seconds: Int,
    amplitude: Float,
    onStopRecording: () -> Unit
) {
    Text(
        text = "Говорите...",
        style = MaterialTheme.typography.headlineSmall,
        color = MaterialTheme.colorScheme.primary
    )

    Spacer(Modifier.height(8.dp))

    Text(
        text = formatSeconds(seconds),
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )

    Spacer(Modifier.height(48.dp))

    MicButton(
        isRecording = true,
        amplitude = amplitude,
        onStartRecording = {},
        onStopRecording = onStopRecording
    )

    Spacer(Modifier.height(24.dp))

    Text(
        text = "Отпустите чтобы сохранить",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )
}

@Composable
private fun ProcessingContent() {
    CircularProgressIndicator(modifier = Modifier.size(64.dp))
    Spacer(Modifier.height(24.dp))
    Text(
        text = "Распознаю...",
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )
}

@Composable
private fun ErrorContent(
    message: String,
    onRetry: () -> Unit,
    onTextInput: () -> Unit
) {
    Text(
        text = "Не удалось распознать",
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.error
    )
    Spacer(Modifier.height(8.dp))
    Text(
        text = message,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center
    )
    Spacer(Modifier.height(32.dp))
    Button(onClick = onRetry) {
        Text("Попробовать ещё раз")
    }
    Spacer(Modifier.height(12.dp))
    OutlinedButton(onClick = onTextInput) {
        Text("Ввести текстом")
    }
}

@Composable
private fun TextInputMode(
    value: String,
    onValueChange: (String) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit
) {
    Text(
        text = "Введите задачу",
        style = MaterialTheme.typography.titleMedium
    )
    Spacer(Modifier.height(16.dp))
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth(),
        placeholder = { Text("Позвонить врачу завтра в 15:00") },
        minLines = 2
    )
    Spacer(Modifier.height(16.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedButton(onClick = onCancel, modifier = Modifier.weight(1f)) {
            Text("Отмена")
        }
        Button(
            onClick = onSave,
            enabled = value.isNotBlank(),
            modifier = Modifier.weight(1f)
        ) {
            Text("Распознать")
        }
    }
}

@Composable
private fun MicButton(
    isRecording: Boolean,
    amplitude: Float,
    onStartRecording: () -> Unit,
    onStopRecording: () -> Unit
) {
    // Пульсация при записи
    val pulseScale by animateFloatAsState(
        targetValue = if (isRecording) 1f + amplitude * 0.4f else 1f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
        label = "pulse"
    )

    val bgColor = if (isRecording)
        MaterialTheme.colorScheme.error
    else
        MaterialTheme.colorScheme.primary

    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(96.dp)
            .scale(pulseScale)
            .background(bgColor, CircleShape)
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        onStartRecording()
                        tryAwaitRelease()
                        onStopRecording()
                    }
                )
            }
    ) {
        Icon(
            imageVector = Icons.Default.Mic,
            contentDescription = if (isRecording) "Запись идёт" else "Начать запись",
            tint = Color.White,
            modifier = Modifier.size(48.dp)
        )
    }
}

private fun formatSeconds(seconds: Int): String {
    val m = seconds / 60
    val s = seconds % 60
    return "%d:%02d".format(m, s)
}
