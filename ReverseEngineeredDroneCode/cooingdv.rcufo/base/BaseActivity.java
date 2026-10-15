package com.cooingdv.rcufo.base;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkInfo;
import android.net.NetworkRequest;
import android.os.Build;
import android.os.Bundle;
import android.text.TextUtils;
import android.widget.Toast;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentActivity;
import androidx.fragment.app.FragmentManager;
import androidx.fragment.app.FragmentTransaction;
import com.cooingdv.rcufo.socket.SocketClient;
import com.cooingdv.rcufo.tools.ActivityStack;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.Dbug;
import com.cooingdv.rcufo.utils.LocalUtil;
import java.util.Locale;

/* JADX INFO: loaded from: classes2.dex */
public class BaseActivity extends FragmentActivity implements IConstants, IActions {
    public String TAG = getClass().getSimpleName();
    public MainApplication mApplication;
    private ConnectivityManager mConnectivityManager;
    private BaseBroadcastCastReceiver mReceiver;
    private Toast mToast;
    private SharedPreferences sharedPreferences;

    private class BaseBroadcastCastReceiver extends BroadcastReceiver {
        private BaseBroadcastCastReceiver() {
        }

        @Override // android.content.BroadcastReceiver
        public void onReceive(Context context, Intent intent) {
            if (BaseActivity.this.isFinishing() || context == null || intent == null) {
                return;
            }
            String action = intent.getAction();
            action.hashCode();
            if (!action.equals("android.net.wifi.STATE_CHANGE")) {
                if (action.equals(IActions.ACTION_QUIT_APP)) {
                    BaseActivity.this.finish();
                    return;
                }
                return;
            }
            NetworkInfo activeNetworkInfo = (NetworkInfo) intent.getParcelableExtra("networkInfo");
            if (activeNetworkInfo == null) {
                if (BaseActivity.this.mConnectivityManager == null) {
                    BaseActivity baseActivity = BaseActivity.this;
                    baseActivity.mConnectivityManager = (ConnectivityManager) baseActivity.getSystemService("connectivity");
                }
                if (BaseActivity.this.mConnectivityManager != null) {
                    activeNetworkInfo = BaseActivity.this.mConnectivityManager.getActiveNetworkInfo();
                }
            }
            if (activeNetworkInfo != null && activeNetworkInfo.getDetailedState() == NetworkInfo.DetailedState.CONNECTED) {
                BaseActivity.this.bindNetwork();
            }
        }
    }

    @Override // androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        getWindow().setFlags(1024, 1024);
        ActivityStack.getInstance().pushActivity(this);
        this.mApplication = (MainApplication) getApplication();
        this.sharedPreferences = PreferencesHelper.getSharedPreferences(getApplicationContext());
        registerBroadCastReceiver();
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onResume() {
        super.onResume();
        if (this.mApplication == null) {
            this.mApplication = (MainApplication) getApplication();
        }
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onDestroy() {
        super.onDestroy();
        ActivityStack.getInstance().popActivity(this);
        if (this.mReceiver != null) {
            getApplicationContext().unregisterReceiver(this.mReceiver);
            this.mReceiver = null;
        }
    }

    private void registerBroadCastReceiver() {
        if (this.mReceiver == null) {
            this.mReceiver = new BaseBroadcastCastReceiver();
        }
        IntentFilter intentFilter = new IntentFilter("android.net.wifi.STATE_CHANGE");
        intentFilter.addAction(IActions.ACTION_QUIT_APP);
        if (Build.VERSION.SDK_INT >= 26) {
            getApplicationContext().registerReceiver(this.mReceiver, intentFilter, 2);
        } else {
            getApplicationContext().registerReceiver(this.mReceiver, intentFilter);
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void bindNetwork() {
        this.mConnectivityManager = (ConnectivityManager) getSystemService("connectivity");
        NetworkRequest.Builder builder = new NetworkRequest.Builder();
        builder.addTransportType(1);
        builder.removeCapability(12);
        NetworkRequest networkRequestBuild = builder.build();
        ConnectivityManager.NetworkCallback networkCallback = new ConnectivityManager.NetworkCallback() { // from class: com.cooingdv.rcufo.base.BaseActivity.1
            @Override // android.net.ConnectivityManager.NetworkCallback
            public void onAvailable(Network network) {
                super.onAvailable(network);
                if (BaseActivity.this.mConnectivityManager != null) {
                    BaseActivity.this.mConnectivityManager.unregisterNetworkCallback(this);
                    BaseActivity.this.mConnectivityManager.bindProcessToNetwork(network);
                }
            }
        };
        ConnectivityManager connectivityManager = this.mConnectivityManager;
        if (connectivityManager != null) {
            connectivityManager.registerNetworkCallback(networkRequestBuild, networkCallback);
        }
    }

    public void showToast(String str, int i) {
        if (TextUtils.isEmpty(str) || isFinishing() || i < 0) {
            return;
        }
        Toast toast = this.mToast;
        if (toast == null) {
            this.mToast = Toast.makeText(getApplicationContext(), str, i);
        } else {
            toast.setText(str);
            this.mToast.setDuration(i);
        }
        this.mToast.setGravity(17, 0, 0);
        this.mToast.show();
    }

    public void showToastShort(String str) {
        showToast(str, 0);
    }

    protected void showToastShort(int i) {
        showToastShort(getResources().getString(i));
    }

    public void showToastLong(String str) {
        showToast(str, 1);
    }

    public void showToastLong(int i) {
        showToastLong(getResources().getString(i));
    }

    public void changeFragment(int i, Fragment fragment, String str, boolean z) {
        FragmentManager supportFragmentManager;
        FragmentTransaction fragmentTransactionBeginTransaction;
        if (fragment == null || isFinishing() || (supportFragmentManager = getSupportFragmentManager()) == null || (fragmentTransactionBeginTransaction = supportFragmentManager.beginTransaction()) == null) {
            return;
        }
        if (!TextUtils.isEmpty(str)) {
            fragmentTransactionBeginTransaction.replace(i, fragment, str);
        } else {
            fragmentTransactionBeginTransaction.replace(i, fragment);
        }
        if (z) {
            fragmentTransactionBeginTransaction.addToBackStack(null);
        }
        fragmentTransactionBeginTransaction.commitAllowingStateLoss();
    }

    public void changeFragment(int i, Fragment fragment) {
        changeFragment(i, fragment, null, true);
    }

    public void release() {
        try {
            ActivityStack.getInstance().clearAllActivity();
            SocketClient.getInstance().stop();
        } catch (Exception e) {
            Dbug.m13285e(this.TAG, "Exception : " + e.getMessage());
            System.exit(0);
        }
    }

    @Override // android.app.Activity, android.view.ContextThemeWrapper, android.content.ContextWrapper
    protected void attachBaseContext(Context context) {
        super.attachBaseContext(AppUtils.attachBaseContext(context));
    }

    public void setLanguage() {
        Locale language = AppUtils.getLanguage(this.sharedPreferences.getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(this)));
        if (language != null) {
            AppUtils.setLanguage(getApplicationContext(), language);
        }
    }
}
