package com.cooingdv.rcufo.fragment;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Message;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentManager;
import androidx.fragment.app.FragmentStatePagerAdapter;
import androidx.viewpager.widget.ViewPager;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.MainActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.LocalUtil;

/* JADX INFO: loaded from: classes2.dex */
public class InstructionsFragment extends BaseFragment implements View.OnClickListener {
    private static final int MSG_UPDATE_UI = 2736;
    private BannerAdapter adapter;
    private InstructionsBroadcastReceiver broadcastReceiver;
    private ImageView btnBack;
    private boolean isChangeLanguage = false;
    private Handler mHandler = new Handler(new Handler.Callback() { // from class: com.cooingdv.rcufo.fragment.InstructionsFragment.1
        @Override // android.os.Handler.Callback
        public boolean handleMessage(Message message) {
            if (InstructionsFragment.this.getActivity() == null || message == null || message.what != InstructionsFragment.MSG_UPDATE_UI) {
                return false;
            }
            InstructionsFragment instructionsFragment = InstructionsFragment.this;
            instructionsFragment.updateCountBar(instructionsFragment.viewPager.getCurrentItem() + 1);
            return false;
        }
    });
    private TextView tvCountBar;
    private ViewPager viewPager;

    private class InstructionsBroadcastReceiver extends BroadcastReceiver {
        private InstructionsBroadcastReceiver() {
        }

        @Override // android.content.BroadcastReceiver
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (TextUtils.isEmpty(action) || context == null || InstructionsFragment.this.getActivity() == null) {
                return;
            }
            action.hashCode();
            if (action.equals(IActions.ACTION_CHANGE_LANGUAGE)) {
                InstructionsFragment.this.isChangeLanguage = true;
                InstructionsFragment.this.initPage();
            }
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_instructions, viewGroup, false);
        this.btnBack = (ImageView) viewInflate.findViewById(C3033R.id.instructions_back);
        this.viewPager = (ViewPager) viewInflate.findViewById(C3033R.id.instructions_view_pager);
        this.tvCountBar = (TextView) viewInflate.findViewById(C3033R.id.instructions_count_bar);
        this.btnBack.setOnClickListener(this);
        return viewInflate;
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() != null) {
            initPage();
            registerBroadcastReceiver();
        }
    }

    private void registerBroadcastReceiver() {
        this.broadcastReceiver = new InstructionsBroadcastReceiver();
        IntentFilter intentFilter = new IntentFilter(IActions.ACTION_CHANGE_LANGUAGE);
        if (Build.VERSION.SDK_INT >= 26) {
            this.mApplication.registerReceiver(this.broadcastReceiver, intentFilter, 2);
        } else {
            this.mApplication.registerReceiver(this.broadcastReceiver, intentFilter);
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void initPage() {
        BannerAdapter bannerAdapter = new BannerAdapter(getChildFragmentManager());
        this.adapter = bannerAdapter;
        this.viewPager.setAdapter(bannerAdapter);
        updateCountBar(this.viewPager.getCurrentItem() + 1);
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
        if (this.broadcastReceiver != null) {
            this.mApplication.unregisterReceiver(this.broadcastReceiver);
        }
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (view == null || getActivity() == null || view.getId() != C3033R.id.instructions_back) {
            return;
        }
        if (this.isChangeLanguage) {
            startActivity(new Intent(getActivity(), (Class<?>) MainActivity.class));
        }
        getActivity().finish();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void updateCountBar(int i) {
        BannerAdapter bannerAdapter = this.adapter;
        if (bannerAdapter != null) {
            String str = String.format(getString(C3033R.string.count_item_format), Integer.valueOf(i), Integer.valueOf(bannerAdapter.getCount()));
            TextView textView = this.tvCountBar;
            if (textView != null) {
                textView.setText(str);
            }
        }
    }

    private class BannerAdapter extends FragmentStatePagerAdapter {
        private int[] images;

        BannerAdapter(FragmentManager fragmentManager) {
            super(fragmentManager);
            int i = PreferencesHelper.getSharedPreferences(InstructionsFragment.this.getActivity().getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(InstructionsFragment.this.getActivity()));
            if (i == 0) {
                this.images = new int[]{C3033R.mipmap.instrucion_chinese_1};
                return;
            }
            if (i == 2) {
                this.images = new int[]{C3033R.mipmap.instrucion_french_1};
                return;
            }
            if (i == 3) {
                this.images = new int[]{C3033R.mipmap.instrucion_german_1};
                return;
            }
            if (i == 4) {
                this.images = new int[]{C3033R.mipmap.instrucion_japanese_1};
                return;
            }
            if (i == 5) {
                this.images = new int[]{C3033R.mipmap.instrucion_spanish_1};
                return;
            }
            if (i == 6) {
                this.images = new int[]{C3033R.mipmap.instrucion_portuguese_1};
            } else if (i == 7) {
                this.images = new int[]{C3033R.mipmap.instrucion_italian_1};
            } else {
                this.images = new int[]{C3033R.mipmap.instrucion_english_1};
            }
        }

        @Override // androidx.viewpager.widget.PagerAdapter
        public int getCount() {
            return this.images.length;
        }

        @Override // androidx.fragment.app.FragmentStatePagerAdapter, androidx.viewpager.widget.PagerAdapter
        public void setPrimaryItem(ViewGroup viewGroup, int i, Object obj) {
            super.setPrimaryItem(viewGroup, i, obj);
            if (InstructionsFragment.this.mHandler != null) {
                InstructionsFragment.this.mHandler.sendEmptyMessage(InstructionsFragment.MSG_UPDATE_UI);
            }
        }

        @Override // androidx.fragment.app.FragmentStatePagerAdapter
        public Fragment getItem(int i) {
            if (i >= getCount()) {
                return null;
            }
            InstructionSubFragment instructionSubFragment = new InstructionSubFragment();
            Bundle bundle = new Bundle();
            bundle.putInt(IConstants.KEY_STEP_NUMBER, i);
            bundle.putInt(IConstants.KEY_RES_ID, this.images[i]);
            instructionSubFragment.setBundle(bundle);
            return instructionSubFragment;
        }
    }
}
