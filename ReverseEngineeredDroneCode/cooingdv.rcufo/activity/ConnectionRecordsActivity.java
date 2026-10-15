package com.cooingdv.rcufo.activity;

import android.content.Context;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.recyclerview.widget.DividerItemDecoration;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseActivity;
import com.cooingdv.rcufo.tools.TimeRecordManager;
import com.cooingdv.rcufo.utils.AppUtils;
import java.util.ArrayList;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class ConnectionRecordsActivity extends BaseActivity implements View.OnClickListener {
    private RecordsAdapter adapter;
    private List<TimeRecordManager.ConnectionRecord> records = new ArrayList();
    private RecyclerView recyclerView;
    private TimeRecordManager timeRecordManager;

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        getWindow().setFlags(1024, 1024);
        setContentView(C3033R.layout.activity_connection_records);
        LinearLayout linearLayout = (LinearLayout) findViewById(C3033R.id.connection_records_layout);
        this.recyclerView = (RecyclerView) findViewById(C3033R.id.connection_records_recycler_view);
        ((ImageView) findViewById(C3033R.id.connection_records_back_btn)).setOnClickListener(this);
        ViewCompat.setOnApplyWindowInsetsListener(linearLayout, new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.ConnectionRecordsActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return ConnectionRecordsActivity.lambda$onCreate$0(view, windowInsetsCompat);
            }
        });
        this.recyclerView.setLayoutManager(new LinearLayoutManager(this));
        this.recyclerView.addItemDecoration(new DividerItemDecoration(this, 1));
        RecordsAdapter recordsAdapter = new RecordsAdapter();
        this.adapter = recordsAdapter;
        this.recyclerView.setAdapter(recordsAdapter);
        this.timeRecordManager = TimeRecordManager.getInstance(this);
        loadRecords();
    }

    static /* synthetic */ WindowInsetsCompat lambda$onCreate$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.systemBars()).right, 0);
        return windowInsetsCompat;
    }

    private void loadRecords() {
        this.records = this.timeRecordManager.getAllRecords();
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onStart() {
        super.onStart();
        setLanguage();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (view.getId() != C3033R.id.connection_records_back_btn) {
            return;
        }
        finish();
    }

    private class RecordsAdapter extends RecyclerView.Adapter<ViewHolder> {
        private RecordsAdapter() {
        }

        @Override // androidx.recyclerview.widget.RecyclerView.Adapter
        public ViewHolder onCreateViewHolder(ViewGroup viewGroup, int i) {
            return new ViewHolder(LayoutInflater.from(viewGroup.getContext()).inflate(C3033R.layout.item_connection_record, viewGroup, false));
        }

        @Override // androidx.recyclerview.widget.RecyclerView.Adapter
        public void onBindViewHolder(ViewHolder viewHolder, int i) {
            viewHolder.bind((TimeRecordManager.ConnectionRecord) ConnectionRecordsActivity.this.records.get(i), i);
        }

        @Override // androidx.recyclerview.widget.RecyclerView.Adapter
        public int getItemCount() {
            return ConnectionRecordsActivity.this.records.size();
        }

        class ViewHolder extends RecyclerView.ViewHolder {
            View itemView;
            TextView tvIndex;
            TextView tvTime;

            ViewHolder(View view) {
                super(view);
                this.itemView = view;
                this.tvIndex = (TextView) view.findViewById(C3033R.id.tv_index);
                this.tvTime = (TextView) view.findViewById(C3033R.id.tv_time);
            }

            void bind(TimeRecordManager.ConnectionRecord connectionRecord, int i) {
                this.tvIndex.setText(String.valueOf(i + 1));
                this.tvTime.setText(connectionRecord.getFormattedTime());
            }
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, android.app.Activity, android.view.ContextThemeWrapper, android.content.ContextWrapper
    protected void attachBaseContext(Context context) {
        super.attachBaseContext(AppUtils.attachBaseContext(context));
    }
}
