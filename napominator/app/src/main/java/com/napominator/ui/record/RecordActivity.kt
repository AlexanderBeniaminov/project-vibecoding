package com.napominator.ui.record

import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import com.napominator.nlp.NlpParser
import com.napominator.ui.confirm.ConfirmScreen
import com.napominator.ui.theme.NapominatorTheme
import dagger.hilt.android.AndroidEntryPoint

/**
 * Активность для голосового ввода.
 * Запускается из FAB на главном экране и из виджета.
 * Показывает RecordScreen → ConfirmScreen → закрывается.
 */
@AndroidEntryPoint
class RecordActivity : ComponentActivity() {

    private val requestPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        // Состояние обновится через ViewModel
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Запрашиваем разрешение на микрофон при старте
        requestPermission.launch(Manifest.permission.RECORD_AUDIO)

        setContent {
            NapominatorTheme {
                var parsedTask by remember { mutableStateOf<NlpParser.ParsedTask?>(null) }

                if (parsedTask == null) {
                    RecordScreen(
                        onRecognized = { parsed -> parsedTask = parsed },
                        onClose = { finish() }
                    )
                } else {
                    ConfirmScreen(
                        parsed = parsedTask!!,
                        onBack = { parsedTask = null },  // вернуться к записи
                        onSaved = { finish() }           // задача сохранена → закрыть
                    )
                }
            }
        }
    }
}
