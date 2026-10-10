package top.hypixice.poros

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import top.hypixice.poros.data.LocaleHelper
import top.hypixice.poros.ui.MicScreen
import top.hypixice.poros.ui.MicViewModel
import top.hypixice.poros.ui.theme.PorosTheme

class MainActivity : ComponentActivity() {

    private val viewModel: MicViewModel by viewModels()

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PorosTheme {
                MicScreen(
                    viewModel = viewModel,
                    onLanguageChanged = { recreate() },
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        viewModel.bind()
    }

    override fun onStop() {
        viewModel.unbind()
        super.onStop()
    }
}
